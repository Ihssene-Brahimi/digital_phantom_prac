# -*- coding: utf-8 -*-
"""intensity_based_stat.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1aohywUs0f8OLEpKowG0kyHcvXzam9cd3
"""

# intensity_based_stat.py

from six.moves import range
from radiomics import base, cMatrices, deprecated
import numpy as np

class IntensityBasedStat(base.RadiomicsFeaturesBase):
  """
  Intensity Based Statistical Features describe the distribution of voxel intensities within the image region defined by the mask
  through commonly used and basic metrics.


  Following additional settings are possible:

  - voxelArrayShift [0]: Integer, This amount is added to the gray level intensity in Energy Intensity in order to prevent negative values.
    If using CT data, or data normalized with mean 0, consider setting this parameter to a fixed value (e.g. 2000) that ensures non-negative
    numbers in the image.

  """

  def __init__(self, inputImage, inputMask, **kwargs):
    super(IntensityBasedStat, self).__init__(inputImage, inputMask, **kwargs)

    self.pixelSpacing = inputImage.GetSpacing()
    self.voxelArrayShift = kwargs.get('voxelArrayShift', 0)
    self.discretizedImageArray = self._applyBinning(self.imageArray.copy())
    self._initCalculation()

  def _initVoxelBasedCalculation(self):
    super(IntensityBasedStat, self)._initVoxelBasedCalculation()

    kernelRadius = self.settings.get('kernelRadius', 1)

    # Get the size of the input, which depends on whether it is in masked mode or not
    if self.masked:
      size = np.max(self.labelledVoxelCoordinates, 1) - np.min(self.labelledVoxelCoordinates, 1) + 1
    else:
      size = np.array(self.imageArray.shape)

    # Take the minimum size along each dimension from either the size of the ROI or the kernel
    boundingBoxSize = np.minimum(size, kernelRadius * 2 + 1)

    # Calculate the offsets, which can be used to generate a list of kernel Coordinates. Shape (Nd, Nk)
    self.kernelOffsets = cMatrices.generate_angles(boundingBoxSize,
                                                   np.array(range(1, kernelRadius + 1)),
                                                   True,  # Bi-directional
                                                   self.settings.get('force2D', False),
                                                   self.settings.get('force2Ddimension', 0))
    self.kernelOffsets = np.append(self.kernelOffsets, [[0, 0, 0]], axis=0)  # add center voxel
    self.kernelOffsets = self.kernelOffsets.transpose((1, 0))

    self.imageArray = self.imageArray.astype('float')
    self.imageArray[~self.maskArray] = np.nan
    self.imageArray = np.pad(self.imageArray,
                                pad_width=self.settings.get('kernelRadius', 1),
                                mode='constant', constant_values=np.nan)
    self.maskArray = np.pad(self.maskArray,
                               pad_width=self.settings.get('kernelRadius', 1),
                               mode='constant', constant_values=False)

  def _initCalculation(self, voxelCoordinates=None):

    if voxelCoordinates is None:
      self.targetVoxelArray = self.imageArray[self.maskArray].astype('float').reshape((1, -1))
      _, p_i = np.unique(self.discretizedImageArray[self.maskArray], return_counts=True)
      p_i = p_i.reshape((1, -1))
    else:
      # voxelCoordinates shape (Nd, Nvox)
      voxelCoordinates = voxelCoordinates.copy() + self.settings.get('kernelRadius', 1)  # adjust for padding
      kernelCoords = self.kernelOffsets[:, None, :] + voxelCoordinates[:, :, None]  # Shape (Nd, Nvox, Nk)
      kernelCoords = tuple(kernelCoords)  # shape (Nd, (Nvox, Nk))

      self.targetVoxelArray = self.imageArray[kernelCoords]  # shape (Nvox, Nk)

      p_i = np.empty((voxelCoordinates.shape[1], len(self.coefficients['grayLevels'])))  # shape (Nvox, Ng)
      for gl_idx, gl in enumerate(self.coefficients['grayLevels']):
        p_i[:, gl_idx] = np.nansum(self.discretizedImageArray[kernelCoords] == gl, 1)

    sumBins = np.sum(p_i, 1, keepdims=True).astype('float')
    sumBins[sumBins == 0] = 1  # Prevent division by 0 errors
    p_i = p_i.astype('float') / sumBins
    self.coefficients['p_i'] = p_i

    self.logger.debug('First order feature class initialized')

  @staticmethod
  def _moment(a, moment=1):
    r"""
    Calculate n-order moment of an array for a given axis
    """

    if moment == 1:
      return np.float(0.0)
    else:
      mn = np.nanmean(a, 1, keepdims=True)
      s = np.power((a - mn), moment)
      return np.nanmean(s, 1)


  def getMeanIntensity(self):
    r"""
    **1. Mean**

    The average gray level intensity within the ROI.
    """

    return np.nanmean(self.targetVoxelArray, 1)


  def getVarianceIntensity(self):
    r"""
    **2. Variance**

    Variance is the the mean of the squared distances of each intensity value from the Mean value. This is a measure of
    the spread of the distribution about the mean. By definition, :math:`\textit{variance} = \sigma^2`
    """

    return np.nanstd(self.targetVoxelArray, 1) ** 2

  def getIntensitySkewness(self):
    r"""
    **3. Skewness**

    Skewness measures the asymmetry of the distribution of values about the Mean value. Depending on where the tail is
    elongated and the mass of the distribution is concentrated, this value can be positive or negative.

    Related links:

    https://en.wikipedia.org/wiki/Skewness

    """

    m2 = self._moment(self.targetVoxelArray, 2)
    m3 = self._moment(self.targetVoxelArray, 3)

    m2[m2 == 0] = 1  # Flat Region, prevent division by 0 errors
    m3[m2 == 0] = 0  # ensure Flat Regions are returned as 0

    return m3 / m2 ** 1.5


  def getIntensityKurtosis(self):
    r"""
    **4. Kurtosis**

    Kurtosis is a measure of the 'peakedness' of the distribution of values in the image ROI. A higher kurtosis implies
    that the mass of the distribution is concentrated towards the tail(s) rather than towards the mean. A lower kurtosis
    implies the reverse: that the mass of the distribution is concentrated towards a spike near the Mean value.

    Related links:

    https://en.wikipedia.org/wiki/Kurtosis

    """

    m2 = self._moment(self.targetVoxelArray, 2)
    m4 = self._moment(self.targetVoxelArray, 4)

    m2[m2 == 0] = 1  # Flat Region, prevent division by 0 errors
    m4[m2 == 0] = 0  # ensure Flat Regions are returned as 0

    return m4 / m2 ** 2.0


  def getMedianIntensity(self):
    r"""
    **5. Median**

    The median gray level intensity within the ROI.
    """

    return np.nanmedian(self.targetVoxelArray, 1)



  def getMinimumIntensity(self):
    r"""
    **6. Minimum**

    """

    return np.nanmin(self.targetVoxelArray, 1)


  def get10IntensityPercentile(self):
    r"""
    **7. 10th percentile**

    The 10th percentile of {X}

    """
    return np.nanpercentile(self.targetVoxelArray, 10, axis=1)


  def get90IntensityPercentile(self):
    r"""
    **8. 90th percentile**

    The 90th percentile of {X}
    """

    return np.nanpercentile(self.targetVoxelArray, 90, axis=1)


  def getMaximumIntensity(self):
    r"""
    **9. Maximum**

    The maximum gray level intensity within the ROI.
    """

    return np.nanmax(self.targetVoxelArray, 1)




  def getIntensityInterquartileRange(self):
    r"""
    **10. Interquartile Range**

    The 25th and 75th percentile of the image array.
    """

    return np.nanpercentile(self.targetVoxelArray, 75, 1) - np.nanpercentile(self.targetVoxelArray, 25, 1)


  def getIntensityRange(self):
    r"""
    **11. Range**

    The range of gray values in the ROI.
    """

    return np.nanmax(self.targetVoxelArray, 1) - np.nanmin(self.targetVoxelArray, 1)


  def getIntensityMeanAbsoluteDeviation(self):
    r"""
    **12. Mean Absolute Deviation (MAD)**

    Mean Absolute Deviation is the mean distance of all intensity values from the Mean Value of the image array.
    """

    u_x = np.nanmean(self.targetVoxelArray, 1, keepdims=True)
    return np.nanmean(np.absolute(self.targetVoxelArray - u_x), 1)


  def getIntensityRobustMeanAbsoluteDeviation(self):
    r"""
    **13. Robust Mean Absolute Deviation (rMAD)**

    Robust Mean Absolute Deviation is the mean distance of all intensity values
    from the Mean Value calculated on the subset of image array with gray levels in between, or equal
    to the 10th and 90th percentile.
    """

    prcnt10 = self.get10IntensityPercentile()
    prcnt90 = self.get90IntensityPercentile()
    percentileArray = self.targetVoxelArray.copy()

    # First get a mask for all valid voxels
    msk = ~np.isnan(percentileArray)
    # Then, update the mask to reflect all valid voxels that are outside the the closed 10-90th percentile range
    msk[msk] = ((percentileArray - prcnt10[:, None])[msk] < 0) | ((percentileArray - prcnt90[:, None])[msk] > 0)
    # Finally, exclude the invalid voxels by setting them to numpy.nan.
    percentileArray[msk] = np.nan

    return np.nanmean(np.absolute(percentileArray - np.nanmean(percentileArray, 1, keepdims=True)), 1)

  def getIntensityMedianAbsoluteDeviation(self):
    r"""
    **14. **

    """
    median_intensity = self.getMedianIntensity()
    return np.nanmedian(np.absolute(self.targetVoxelArray - median_intensity[:, None]), 1)


  def getIntensityCoefficientOfVariation(self):
    r"""
    **15. **


    """
    mean_intensity = self.getMeanIntensity()
    std_intensity = self.getStandardDeviationIntensity()
    return np.nan_to_num(std_intensity / mean_intensity, nan=0, posinf=0, neginf=0)



  def getIntensityQuartileCoefficientOfDispersion(self):
    r"""
    **16. **


    """
    q75_intensity = np.nanpercentile(self.targetVoxelArray, 75, axis=1)
    q25_intensity = np.nanpercentile(self.targetVoxelArray, 25, axis=1)
    return np.nan_to_num((q75_intensity - q25_intensity) / (q75_intensity + q25_intensity), nan=0, posinf=0, neginf=0)



  def getIntensityEnergy(self):
      r"""
      **17. Energy**

      Energy is a measure of the magnitude of voxel values in an image. A larger values implies a greater sum of the
      squares of these values.

      """

      shiftedParameterArray = self.targetVoxelArray + self.voxelArrayShift

      return np.nansum(shiftedParameterArray ** 2, 1)


  def getRootMeanSquareIntensity(self):
    r"""
    **18. Root Mean Squared (RMS)**

    RMS is the square-root of the mean of all the squared intensity values. It is another measure of the magnitude of
    the image values.

    """

    # If no voxels are segmented, prevent division by 0 and return 0
    if self.targetVoxelArray.size == 0:
      return 0

    shiftedParameterArray = self.targetVoxelArray + self.voxelArrayShift
    Nvox = np.sum(~np.isnan(self.targetVoxelArray), 1).astype('float')
    return np.sqrt(np.nansum(shiftedParameterArray ** 2, 1) / Nvox)


  def getStandardDeviationIntensity(self):
    r"""
    **19. Standard Deviation**

    Standard Deviation measures the amount of variation or dispersion from the Mean Value.

    """

    return np.nanstd(self.targetVoxelArray, axis=1)