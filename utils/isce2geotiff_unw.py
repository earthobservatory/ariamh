#!/usr/bin/env python3
"""
Map tiler PGE wrapper to generate map tiles following the
OSGeo Tile Map Service Specification.
"""

from subprocess import check_call
import os, sys, argparse, logging, traceback, glob
import numpy as np
from osgeo import gdal
from gdalconst import GA_ReadOnly


gdal.UseExceptions() # make GDAL raise python exceptions
log_format = "[%(asctime)s: %(levelname)s/%(funcName)s] %(message)s"
logging.basicConfig(format=log_format, level=logging.INFO)
logger = logging.getLogger('create_raster')


BASE_PATH = os.path.dirname(__file__)


def call_noerr(cmd):
    """Run command and warn if exit status is not 0."""

    try: check_call(cmd, shell=True)
    except Exception as e:
        logger.warn("Got exception running {}: {}".format(cmd, str(e)))
        logger.warn("Traceback: {}".format(traceback.format_exc()))


def get_clims(raster, band, clim_min_pct=None, clim_max_pct=None, nodata=None):
    """Get data absolute min/max values as well as min/max percentile values
       for a given GDAL-recognized file format for a particular band."""

    # load raster
    gd = gdal.Open(raster, GA_ReadOnly)

    # get number of bands
    bands = gd.RasterCount

    # process the raster
    b = gd.GetRasterBand(band)
    d = b.ReadAsArray()
    logger.info("band data: {}".format(d))
    # fetch max and min
    # min = band.GetMinimum()
    # max = band.GetMaximum()
    if nodata is not None:
        d = np.ma.masked_equal(d, nodata)
    min = np.amin(d)
    max = np.amax(d)
    min_pct = np.percentile(d, clim_min_pct) if clim_min_pct is not None else None
    max_pct = np.percentile(d, clim_max_pct) if clim_max_pct is not None else None

    logger.info("band {} absolute min/max: {} {}".format(band, min, max))
    logger.info("band {} {}/{} percentiles: {} {}".format(band, clim_min_pct,
                                                          clim_max_pct, min_pct,
                                                          max_pct))
    gd = None

    return min, max, min_pct, max_pct

def create_raster(raster, band=1, cmap='jet', clim_min=None,
                 clim_max=None, clim_min_pct=None, clim_max_pct=None,
                  nodata=None):
    """Generate map tiles following the OSGeo Tile Map Service Specification."""

    # check mutually exclusive args
    if clim_min is not None and clim_min_pct is not None:
        raise(RuntimeError("Cannot specify both clim_min and clim_min_pct."))
    if clim_max is not None and clim_max_pct is not None:
        raise(RuntimeError("Cannot specify both clim_max and clim_max_pct."))

    # get clim
    min, max, min_pct, max_pct = get_clims(raster, band,
                                           clim_min_pct if clim_min_pct is not None else 20,
                                           clim_max_pct if clim_max_pct is not None else 80,
                                           nodata)

    # overwrite if options not specified
    if clim_min is not None: min = clim_min
    if clim_max is not None: max = clim_max
    if clim_min_pct is not None: min = min_pct
    if clim_max_pct is not None: max = max_pct

    # convert to geotiff
    logger.info("Generating GeoTIFF.")
    tif_file = "{}.tif".format(os.path.basename(raster))
    if os.path.exists(tif_file): os.unlink(tif_file)
    cmd = "isce2geotiff.py -i {} -o {} -c {:f} {:f} -b {} -m {}"
    check_call(cmd.format(raster, tif_file, min, max, band-1, cmap), shell=True)

def check_files(root_file):
    hdr_file = root_file + '.hdr'
    vrt_file = root_file + '.vrt'
    xml_file = root_file + '.xml'
    if os.path.isfile(root_file) & os.path.isfile(hdr_file) & os.path.isfile(vrt_file) & os.path.isfile(xml_file):
        return True
    else:
        return False

def rm_files(glob_string):
    files = glob.glob(glob_string)
    for i in files:
        os.remove(i)


def intf2browse(prod_path, mask=True):
    # isce_path = os.path.abspath(inps.isce)
    print('Identifying files and directories available')
    # file_list = glob.glob(file_in)
    # print('Found the following files: {}'.format(file_list))
    # dir_list = [os.path.dirname(os.path.abspath(file_list[0]))]
    # for i in file_list:
    #     dir = os.path.dirname(os.path.abspath(i))
    #     if dir not in dir_list:
    #         dir_list.append(dir)
    prod_name = os.path.dirname(os.path.abspath(prod_path))
    print('Found the following directories: {}\n'.format(prod_path))
    file_list_sorted = []
    # for i in range(len(dir_list)):
    print('\nProcessing for {}\n'.format(prod_path))
    # file_list_new = [x for x in file_list if prod_path.split('/')[-1] in x]
    option1 = ''
    option2 = ''
    if mask:
        print('Water body masking option is specified, checking for masking files')
        mask_file = prod_path + '/filt_topophase.unw.conncomp.geo'
        if not check_files(mask_file):
            raise Exception(
                'Missing filt_topophase.unw.conncomp.geo/.hdr/.vrt/.xml for water body masking in: {}'.format(
                    prod_path))
        else:
            print('Masking files are present')
        option1 = '*(b>0)'
        option2 = ' --b={}'.format(mask_file)
    if check_files(prod_path+ '/filt_topophase.unw.geo'):
        print('Converting unwrapped interferogram in {}'.format(prod_path))
        in_file = prod_path + '/filt_topophase.unw.geo'
        out_file = 'filt_topophase.unw.out.geo'
        check_call("imageMath.py -e='a_1{}' --a={}{} -o {} -t FLOAT -s BIL".format(
            option1, in_file, option2, out_file), shell=True)
        status = create_raster(out_file, 1, nodata=0)
        # check_call("python3 {} {} -b 1 --nodata 0".format(isce_path, out_file), shell=True)
        check_call("mv filt_topophase.unw.out.geo.tif {}/filt_topophase.unw.geo.tif".format(prod_path),
                   shell=True)
        print('DONE')
    if check_files(prod_path + '/filt_topophase.flat.geo'):
        print('Converting wrapped interferogram in {}'.format(prod_path))
        in_file = prod_path + '/filt_topophase.flat.geo'
        out_file = 'filt_topophase.flat.out.geo'
        check_call("imageMath.py -e='abs(a); arg(a){}' --a={}{} -o {} -t FLOAT -s BIL".format(
            option1, in_file, option2, out_file), shell=True)
        status = create_raster(out_file, 2, nodata=0)
        check_call("mv filt_topophase.flat.out.geo.tif {}/filt_topophase.flat.geo.tif".format(prod_path),
                   shell=True)
        print('DONE')
    # if check_files(prod_path + '/phsig.cor.geo'):
    #     print('Converting phsig.cor.geo in {}'.format(prod_path))
    #     in_file = prod_path + '/phsig.cor.geo'
    #     status = create_raster(in_file, 1, nodata=0)
    #     check_call("mv phsig.cor.geo.tif {}/phsig.cor.geo.tif".format(prod_path),shell=True)
    print('Cleaning directory\n')
    rm_files('*.out.geo*')

    # print('converting tif rasters to png')
    # for tif_file in glob.glob("{}/*.tif".format(prod_path)):
    #     check_call("gdal_translate -of png {} {}.browse.png".format(tif_file,os.path.splitext(tif_file)[0]),shell=True)

    # rm_files('phsig.cor.geo*')
    print('\nEND aria_intf2geotiff.py\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raster", help="input raster file (any GDAL-recognized file format)")
    parser.add_argument("-b", "--band", dest="band", type=int,
                        default=1, help="raster band")
    parser.add_argument("-m", "--cmap", dest="cmap", type=str,
                        default='jet', help="matplotlib colormap")
    parser.add_argument("--clim_min", dest="clim_min", type=float,
                        default=None, help="color limit min value")
    parser.add_argument("--clim_max", dest="clim_max", type=float,
                        default=None, help="color limit max value")
    parser.add_argument("--clim_min_pct", dest="clim_min_pct", type=float,
                        default=None, help="color limit min percent")
    parser.add_argument("--clim_max_pct", dest="clim_max_pct", type=float,
                        default=None, help="color limit max percent")
    parser.add_argument("--nodata", dest="nodata", type=float,
                        default=None, help="nodata value")
    args = parser.parse_args()
    status = create_raster(args.raster, args.band, args.cmap,
                          args.clim_min, args.clim_max, args.clim_min_pct,
                          args.clim_max_pct,  args.nodata)

