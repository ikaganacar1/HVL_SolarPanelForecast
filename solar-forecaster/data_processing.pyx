# data_processing.pyx

import numpy as np
cimport numpy as np
cimport cython

# Cython'un güvenlik kontrollerini hız için devre dışı bırak
@cython.boundscheck(False)
@cython.wraparound(False)
def fast_resample_hourly(np.ndarray[np.int64_t] timestamps, np.ndarray[np.float64_t] values):
    """
    NumPy dizilerini kullanarak saatlik yeniden örnekleme (resampling) yapar.
    Pandas'tan çok daha hızlıdır.

    Args:
        timestamps: Zaman damgaları (nanosaniye cinsinden int64).
        values: Karşılık gelen değerler (float64).

    Returns:
        tuple: (sonuç_zaman_damgaları, sonuç_değerleri)
    """
    # Sonuçları saklamak için Python listeleri
    cdef list result_timestamps = []
    cdef list result_values = []
    
    # Döngü değişkenleri
    cdef Py_ssize_t i, n
    n = timestamps.shape[0]
    
    if n == 0:
        return result_timestamps, result_values
        
    # Saatlik aralık (nanosaniye cinsinden)
    cdef long long ONE_HOUR_NS = 3600 * 1_000_000_000

    # Mevcut saat aralığı için değişkenler
    cdef long long current_hour_start
    cdef double current_sum = 0.0
    cdef int current_count = 0
    
    # İlk saat aralığını başlat
    current_hour_start = (timestamps[0] // ONE_HOUR_NS) * ONE_HOUR_NS
    
    # Veri üzerinde döngü
    for i in range(n):
        # Eğer yeni bir saat aralığına girdiysek...
        if timestamps[i] >= current_hour_start + ONE_HOUR_NS:
            # Önceki aralığın ortalamasını kaydet (eğer veri varsa)
            if current_count > 0:
                result_timestamps.append(current_hour_start)
                result_values.append(current_sum / current_count)
            
            # Yeni aralığı başlat
            current_hour_start = (timestamps[i] // ONE_HOUR_NS) * ONE_HOUR_NS
            current_sum = values[i]
            current_count = 1
        else:
            # Aynı aralıkta devam et
            current_sum += values[i]
            current_count += 1
            
    # Döngü bittikten sonra son aralığı da kaydet
    if current_count > 0:
        result_timestamps.append(current_hour_start)
        result_values.append(current_sum / current_count)
        
    return result_timestamps, result_values