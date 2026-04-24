# File containing the UFF class.
# Used to store data and metadata.

from zipfile import ZipFile

from .constants import *
from .jpk.loadjpkcurve import loadJPKcurve
from .jpk.loadjpkimg import computeJPKPiezoImg
from .jpk_h5.jpkh5piezoimg import computeJPKPiezoImg_h5
from .jpk_h5.loadjpkh5curve import loadJPKh5curve

from .nanosc.loadnanosccurve import loadNANOSCcurve
from .nanosc.loadnanoscimg import loadNANOSCimg
from .ps_nex.loadpsnexcurve import loadPSNEXcurve
from .hs3.loadHS3curve import loadHS3curve
from .ardf.loadARDFcurve import loadARDFcurve
from .ardf.loadARDFimg import loadARDFimg
from .ardf.loadibwcurve import loadIBWcurve
from .load_uff import loadUFFcurve
from .save_uff import saveUFFtxt
#  from .ps_nex.loadpsneximg import loadPSNEXimg


class UFF:
    """
    Class used to store the data and metadata of an AFM file.

            Properties:
                    filemetadata (dict): Dictionary containing the file metadata.
                    isFV (bool): Flag indicating if the file is a Force Volume or not.
                    piezoimg (np.array): 2D np.array containing the piezo image of the file.
                    imagedata (dict): dictionary containing additional image data.

            Methods:
                    getcurve
                    getpiezoimg
                    to_txt

    """

    def __init__(self):
        self.filemetadata = None
        # JPK Specific Atributes
        self._sharedataprops = None
        self._groupedpaths = None
        # FV Specific Atribtues
        self.isFV = None
        self.piezoimg = None
        self.df_map = None  # PS-NEX specific: DataFrame with curve mappings
        # In files like JPK scans you may
        # have additional image data.
        self.imagedata = None
        self.bool_correct_overshoot = False
        self._curve_cache = None  # Cache for loaded curves to avoid reloading 

    def _loadcurve(self, curveidx, afmfile, file_type):
        """
        Hidden function used to load a single curve from a file.
        bool_correct_overshoot is used to correct the overshoot in PS-NEX files.

        Supported formats:
            - JPK --> .jpk-force, .jpk-force-map, .jpk-qi-data
            - NANOSCOPE --> .spm, .pfc
            - UFF --> .uff
            - PS-NEX --> .tdms
            - HS-3 --> .tdms
            - IBW --> .ibw
            - ARDF --> .ARDF

                Parameters:
                        curveidx (int): Index of curve to load.
                        afmfile (ZipFile): Buffer containing the data of the AFM file. Only used for JPK files.
                        file_type (str): File extension.
                        bool_correct_overshoot (bool): Flag indicating whether to correct overshoot.

                Returns:
                        FC (utils.forcecurve.ForceCurve): ForceCurve object containing the force curve data.
        """
        if file_type in jpkfiles:
            curvepaths = self._groupedpaths[curveidx]
            FC = loadJPKcurve(
                curvepaths, afmfile, curveidx, self.filemetadata
            )
        elif file_type in jpk_h5_file:
            FC = loadJPKh5curve(self.filemetadata, curveidx)
        elif file_type[1:].isdigit() or file_type in nanoscfiles:
            FC = loadNANOSCcurve(curveidx, self.filemetadata)
        elif file_type in ufffiles:
            FC = loadUFFcurve(self.filemetadata)
        elif file_type in psnexfiles:
            FC = loadPSNEXcurve(self.filemetadata, curveidx, bool_correct_overshoot=self.bool_correct_overshoot)
        elif file_type in hs3files:
            FC = loadHS3curve(self.filemetadata, curveidx)
        elif file_type in ibwfiles:
            FC = loadIBWcurve(self.filemetadata, curveidx)
        elif file_type in ARDFfiles:
            FC = loadARDFcurve(self.filemetadata, curveidx)
        return FC

    def getcurve(self, curveidx, bool_correct_overshoot=False):
        """
        Function used to load a single curve from a file.

        Supported formats:
            - JPK --> .jpk-force, .jpk-force-map, .jpk-qi-data
            - NANOSCOPE --> .spm, .pfc
            - UFF --> .uff
            - PS-NEX --> .tdms
            - HS-3 --> .tdms
            - IBW --> .ibw
            - ARDF --> .ARDF

                Parameters:
                        curveidx (int): Index of curve to load.
                        bool_correct_overshoot (bool): Flag indicating whether to correct overshoot.

                Returns:
                        FC (utils.forcecurve.ForceCurve): ForceCurve object containing the force curve data.
        """
        # Check if bool_correct_overshoot changed state
        if self.bool_correct_overshoot != bool_correct_overshoot:
            self._curve_cache = None  # Clear cache if correction state changes
        
        self.bool_correct_overshoot = bool_correct_overshoot
        file_type = self.filemetadata['file_type']
        
        if file_type in jpkfiles:
            with open(self.filemetadata['file_path'], 'rb') as file:
                afmfile = ZipFile(file)
                curvepaths = self._groupedpaths[curveidx]
                FC = loadJPKcurve(
                    curvepaths, afmfile, curveidx, self.filemetadata)
            
        elif file_type in jpk_h5_file:
            FC = loadJPKh5curve(self.filemetadata, curveidx)
        elif file_type[1:].isdigit() or file_type in nanoscfiles:
            FC = loadNANOSCcurve(curveidx, self.filemetadata)
        elif file_type in ufffiles:
            FC = loadUFFcurve(self.filemetadata)
        elif file_type in psnexfiles:
            if self._curve_cache is not None and self.bool_correct_overshoot == bool_correct_overshoot:
                # If curve is already cached with same correction state, return it
                FC = self._curve_cache
            else:
                FC = loadPSNEXcurve(self.filemetadata, curveidx, bool_correct_overshoot=self.bool_correct_overshoot)
                self._curve_cache = FC
        elif file_type in hs3files:
            FC = loadHS3curve(self.filemetadata, curveidx)
        elif file_type in ibwfiles:
            FC = loadIBWcurve(self.filemetadata, curveidx)
        elif file_type in ARDFfiles:
            FC = loadARDFcurve(self.filemetadata, curveidx)
        
        return FC

    def getpiezoimg(self):
        """
        Function used to compute the piezo image of a file.

        It is required that the file is a Force Volume.

        Supported formats:
            - JPK --> .jpk-force-map, .jpk-qi-data
            - JPK H5 --> .h5-jpk
            - NANOSCOPE --> .spm, .pfc
            - PS-NEX --> .tdms
            - Asylum Research --> .ARDF

                Parameters: None

                Returns:
                        piezoimg (np.array): 2D array containing the piezo image of the file.
                        df_map (pd.DataFrame): DataFrame with curve mappings (PS-NEX only, None for others).
        """
        file_type = self.filemetadata['file_type']
        if file_type in jpkfiles:
            self.piezoimg = computeJPKPiezoImg(self)
        elif file_type in jpk_h5_file:
            self.piezoimg = computeJPKPiezoImg_h5(self)
        elif file_type[1:].isdigit() or file_type in nanoscfiles:
            self.piezoimg = loadNANOSCimg(self.filemetadata)
        elif file_type in psnexfiles:
            from .ps_nex.loadpsneximg import loadPSNEXimg
            self.piezoimg, self.df_map = loadPSNEXimg(self)
        elif file_type in ARDFfiles:
            self.piezoimg = loadARDFimg(self.filemetadata)
        return self.piezoimg, self.df_map

    def getcurve_by_index(self, curve_index, z_sensor_delay=0, bool_correct_overshoot=False):
        """
        Load a single force curve from a PS-NEX map by curve_index from df_map.
        
        This method links getcurve() with df_map by using the curve_index to look up
        the corresponding TDMS file path and load the curve data. This is particularly
        useful for PS-NEX maps where each curve is stored in a separate TDMS file.
        
        The method first checks if df_map is available (call getpiezoimg() first if not).
        Then uses the curve_index to find the corresponding file and loads the force curve.
        
        Parameters:
        -----------
        curve_index : int
            The curve index to load (must exist in df_map). This is typically a value 
            between 0 and len(df_map)-1.
        z_sensor_delay : float, optional
            Z sensor delay value. Default is 0.
        bool_correct_overshoot : bool, optional
            Flag indicating whether to correct overshoot. Default is False.
        
        Returns:
        --------
        force_curve : utils.forcecurve.ForceCurve
            The loaded force curve object
        metadata : dict
            Metadata from the loaded TDMS file
        filepath : str
            Path to the TDMS file that was loaded
        
        Raises:
        -------
        ValueError
            If df_map is not available or curve_index is not found in df_map
        RuntimeError
            If file type is not PS-NEX
        
        Examples:
        ---------
        >>> # Load piezo image and df_map first
        >>> piezoimg, df_map = uff_map.getpiezoimg()
        >>> 
        >>> # Load a specific curve by index
        >>> fc, metadata, filepath = uff_map.getcurve_by_index(curve_index=5)
        >>> 
        >>> # With overshoot correction
        >>> fc, metadata, filepath = uff_map.getcurve_by_index(
        ...     curve_index=5, 
        ...     bool_correct_overshoot=True
        ... )
        """
        # Check if df_map exists
        if self.df_map is None:
            raise ValueError(
                "df_map not available. Call getpiezoimg() first to load the map data."
            )
        
        # Check file type
        file_type = self.filemetadata['file_type']
        if file_type not in psnexfiles:
            raise RuntimeError(
                f"getcurve_by_index() is only supported for PS-NEX files. "
                f"Current file type: {file_type}"
            )
        
        # Import the helper function
        from .ps_nex.loadpsnexcurve import loadPSNEXcurve_by_index
        
        # Load the curve using the helper function
        force_curve, metadata, filepath = loadPSNEXcurve_by_index(
            self.df_map,
            curve_index,
            z_sensor_delay=z_sensor_delay,
            bool_correct_overshoot=bool_correct_overshoot
        )
        
        return force_curve, metadata, filepath

    def to_txt(self, savedir):
        """
        Function used to save the loaded data into a txt file following the UFF.

                Parameters:
                        savedir (str): Path to save the txt UFF file.

                Returns: None
        """
        if self.isFV:
            for curveidx in range(self.filemetadata['Entry_tot_nb_curve']):
                saveUFFtxt(self, self, savedir, curveidx)
        else:
            saveUFFtxt(self, self, savedir)
