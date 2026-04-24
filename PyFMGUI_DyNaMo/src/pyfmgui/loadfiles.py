# Import logging and get global logger
import logging
# Import for multiprocessing
import concurrent.futures
import os
# Get loadfile function from PyFMReader
from pyfmreader import loadfile
# Get constants
import pyfmgui.const as const

logger = logging.getLogger()


def _collapse_psnex_map_files(filepaths):
    """
    Keep a single representative TDMS file per PS-NEX map folder.

    A PS-NEX force map stores one curve per TDMS file inside a map folder
    (typically named like psnex_map_*). Loading all TDMS files as independent
    datasets makes the same map load repeatedly.
    """
    collapsed = []
    seen_psnex_folders = set()

    for path in filepaths:
        parent = os.path.basename(os.path.dirname(path))
        is_tdms = path.lower().endswith('.tdms')

        if is_tdms and 'psnex_map_' in parent:
            folder_key = os.path.dirname(path)
            if folder_key in seen_psnex_folders:
                continue
            seen_psnex_folders.add(folder_key)
        collapsed.append(path)

    return collapsed

def load_single_file(filepath):
    try:
        file = loadfile(filepath)
        file_id = file.filemetadata['Entry_filename']
        file_type = file.filemetadata['file_type']
        if file.isFV and file_type in const.nanoscope_file_extensions:
            file.getpiezoimg()
        if file.isFV and file_type in const.asylum_file_extensions:
            file.getpiezoimg()
        return (file_id, file)
    except Exception as error:
        logger.info(f'Failed to load {filepath} with error: {error}')
        return None

def loadfiles(session, filelist, progress_callback, range_callback, step_callback):
    files_to_load = [path for path in filelist if path not in session.loaded_files_paths]
    files_to_load = _collapse_psnex_map_files(files_to_load)
    loaded_files = []
    count = 0
    with concurrent.futures.ProcessPoolExecutor() as executor:
        # loaded_files = executor.map(load_single_file, files_to_load)
        futures = [executor.submit(load_single_file, filepath) for filepath in files_to_load]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result is not None:
                loaded_files.append(result)
            count+=1
            progress_callback.emit(count)
    # loaded_files = list(loaded_files)
    # Loop and save files in the session
    for file_id, file in loaded_files:
        session.loaded_files[file_id] = file
        session.loaded_files_paths.append(file.filemetadata.get('file_path'))
