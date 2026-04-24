"""
Created on Thu Apr 7 10:56:00 2026

@author: Lorenzo

derived from the JPK file img. Still need to improve this
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import shutil
import pyfmreader.ps_nex.loadpsnexMaps as maps
import os
import glob
import logging

logger = logging.getLogger()

# As for 20/07/2022 these are the accepted channels for
# JPK files. This routine has a lot of hard coded values
# i.e: offset to search for the conversion factors, that are
# susceptible to breaking if the format is modified in any way.
# valid_channels = [
#     'Baseline', 'Height(measured)', 'SlopeFit', 'Adhesion', 'Height'
# ]

# valid_scalings = [
#     'Force', 'volts', 'Calibrated height', 'Nominal height'
# ]

# height_channels = [
#     'Height(measured)', 'Height'
# ]

# valid_height_scalings = [
#     'Calibrated height', 'Nominal height'
# ]

# valid_vars_channels = [
#     'Baseline', 'SlopeFit', 'Adhesion'
# ]

# valid_vars_scalings = [
#     'Force', 'volts'
# ]


def loadPSNEXimg(UFF):
    """
    Function used to load the piezo image from a PS-NEX map directory.
    
    For PSNEX maps, the data is stored as TDMS files in a directory (psnex_map_*).
    Each TDMS file represents one force curve at one pixel location.
    This function loads all TDMS files, extracts height data, and builds
    a 2D piezo image array. The returned df_map contains metadata and filepath
    mappings for each curve, enabling interactive access to individual force curves.
    
    The image is returned in 3D format (height, width, 1) to match the output 
    format of other file types (JPK, ARDF, etc.).
    
            Parameters:
                    UFF (uff.UFF): UFF object containing the PS-NEX file metadata.
            
            Returns:
                    piezoimg (np.array): 3D array (h, w, 1) containing the piezo image.
                    df_map (pd.DataFrame): DataFrame with columns:
                        - filepath: Path to the TDMS file for this curve
                        - curve_index: Sequential index (0 to num_curves-1)
                        - x_index: Pixel X coordinate
                        - y_index: Pixel Y coordinate
                        - z_height_um_zero / z_height_um: Height data for heatmap
                        - Other measurement columns from TDMS files
    """
    try:
        filepath = UFF.filemetadata['file_path']
        
        # Determine map directory
        if filepath.endswith('.tdms'):
            map_directory = os.path.dirname(filepath)
        else:
            map_directory = filepath
        
        if not os.path.isdir(map_directory):
            logger.warning(f"Map directory not found: {map_directory}")
            return None, None
        
        logger.info(f"Loading PSNEX map from: {map_directory}")
        
        # Load map file data using the maps module
        df_map, map_x_pix, map_y_pix, params = maps.load_map_file_square_tdms(map_directory)
        
        if df_map is None:
            logger.warning(f"Failed to load PSNEX map from {map_directory}")
            return None, None
        
        # Ensure df_map has a copy to avoid warnings
        df_map = df_map.copy()
        
        # Check map integrity and fix if needed
        bool_error, _ = maps.check_map_indice_integrity(df_map, map_x_pix, map_y_pix)
        
        if bool_error:
            logger.info("Map indices integrity error detected. Regenerating indices...")
            # Regenerate positions
            x_pos_1d, y_pos_1d, curve_index = maps.generate_xy_map_positions(
                map_x_pix=map_x_pix, 
                map_y_pix=map_y_pix
            )
            
            # Try to sort by time
            try:
                df_time = maps.compute_time_difference(map_directory)
                df_time = df_time.drop_duplicates(subset='filepath', keep='first')
                df_map = pd.merge(df_map, df_time, on='filepath', how='left')
            except Exception as e:
                logger.debug(f"Could not sort by time: {e}")
            
            df_map['x_index'] = x_pos_1d
            df_map['y_index'] = y_pos_1d
            df_map['curve_index'] = curve_index
        else:
            logger.info("Map indices are valid. Using existing indices.")
        
        # Ensure curve_index exists (sequential index mapping to pixel location)
        if 'curve_index' not in df_map.columns:
            df_map['curve_index'] = range(len(df_map))
        
        # Ensure x_index and y_index exist and are valid
        if 'x_index' not in df_map.columns or 'y_index' not in df_map.columns:
            logger.info("Generating x_index and y_index from curve_index...")
            x_indices = df_map['curve_index'].values % map_x_pix
            y_indices = df_map['curve_index'].values // map_x_pix
            df_map['x_index'] = x_indices
            df_map['y_index'] = y_indices
        else:
            # Validate existing indices
            try:
                df_map['x_index'] = df_map['x_index'].astype(int)
                df_map['y_index'] = df_map['y_index'].astype(int)
                # Check if indices are in valid range
                if (df_map['x_index'] < 0).any() or (df_map['x_index'] >= map_x_pix).any():
                    logger.warning("x_index out of range. Regenerating...")
                    x_indices = df_map['curve_index'].values % map_x_pix
                    df_map['x_index'] = x_indices
                if (df_map['y_index'] < 0).any() or (df_map['y_index'] >= map_y_pix).any():
                    logger.warning("y_index out of range. Regenerating...")
                    y_indices = df_map['curve_index'].values // map_x_pix
                    df_map['y_index'] = y_indices
            except Exception as e:
                logger.warning(f"Error validating indices: {e}. Regenerating...")
                x_indices = df_map['curve_index'].values % map_x_pix
                y_indices = df_map['curve_index'].values // map_x_pix
                df_map['x_index'] = x_indices
                df_map['y_index'] = y_indices
        
        # Extract height data
        height_key = 'z_height_um_zero' if 'z_height_um_zero' in df_map.columns else 'z_height_um'
        
        if height_key not in df_map.columns:
            logger.warning(f"Height column '{height_key}' not found in map data")
            return None, df_map
        
        z_values = df_map[height_key].values
        
        # Get pixel indices from df_map (guaranteed to exist now)
        x_indices = df_map['x_index'].values
        y_indices = df_map['y_index'].values
        
        # Create 2D array
        piezoimg = np.zeros((map_y_pix, map_x_pix), dtype=np.float64)
        
        for i in range(len(z_values)):
            x_idx = int(x_indices[i])
            y_idx = int(y_indices[i])
            
            if 0 <= x_idx < map_x_pix and 0 <= y_idx < map_y_pix:
                value = z_values[i]
                if not np.isnan(value):
                    piezoimg[y_idx, x_idx] = value
        
        # Normalize to zero minimum (subtract minimum value)
        piezoimg = piezoimg - np.nanmin(piezoimg)
        
        # Convert to 3D (h, w, 1) to match output format of other file types
        piezoimg_3d = np.expand_dims(piezoimg, axis=2)
        
        logger.info(f"Successfully loaded PSNEX map with shape: {piezoimg_3d.shape}")
        logger.debug(f"df_map columns: {list(df_map.columns)}")
        logger.debug(f"df_map shape: {df_map.shape}")
        return piezoimg_3d, df_map
        
    except Exception as e:
        import traceback
        logger.error(f"Error loading PSNEX image: {e}")
        logger.debug(traceback.format_exc())
        return None, None



def createPSNEXimgcsv(UFF):
    """
    Function used to create a CSV map file, if it does not already exist, from a PS-NEX file. If Map
    file already exists, it will not be overwritten. Function will check the force curve files in the 
    directory path of the current PS-NEX file. The CSV fill will be placed in the same directory.

            Parameters:
                    UFF (uff.UFF): UFF object containing the PS-NEX file metadata.
            
            Returns:
                    piezoimg (np.array): 2D array containing the piezo image.
    """
    # for testing purposes
    CSVfile = False

    filepath = UFF.filemetadata['file_path']
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File {filepath} does not exist.")
    
    if UFF.filemetadata['mapping_bool']:
        print("This is a psnex mapping file! ")



    # pattern = os.path.join(filepath, 'psnex_map__*')
    directory = os.path.dirname(filepath)
    print (f"directory: {directory}")
    # files = [f for f in glob.glob(pattern) if not f.endswith('.zip')]
    files = [f for f in glob.glob(os.path.join(directory, '*.tdms')) if f.endswith('.tdms')]

    # if actual map path was given, use that
    if files == []:
        # if no files were found, check if the directory is a valid path
        files.append(filepath)
    
    data = maps.load_map_file_square_tdms_v2(directory)
    experiment_name = UFF.filemetadata['Entry_experiment_name']

    if not experiment_name:
        experiment_name = ''

    # Construct the CSV filename
    csv_filename = os.path.join(directory, f"{os.path.basename(directory)}_{experiment_name}.csv")
    print(csv_filename)


    # Save the DataFrame to CSV with 6 significant digits
    data.to_csv(csv_filename, index=False, float_format='%.6g')
    csv_filepath = csv_filename
    
    piezoimg = np.array(data['Z_height_um_zero']).reshape((UFF.filemetadata['num_y_pixels'], UFF.filemetadata['num_x_pixels']))
    print('done')
    return piezoimg , data