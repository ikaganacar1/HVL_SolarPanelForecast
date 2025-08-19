import numpy as np
cimport numpy as cnp
cimport cython
from libc.math cimport fmin, fmax

# C türleri için type definitions
ctypedef cnp.float64_t DTYPE_t

@cython.boundscheck(False)  # Bounds checking'i kapat (hız için)
@cython.wraparound(False)   # Negative indexing'i kapat
@cython.cdivision(True)     # C-style division kullan
def fast_battery_simulation(
    cnp.ndarray[DTYPE_t, ndim=1] solar_power_normalized,
    cnp.ndarray[cnp.int64_t, ndim=1] night_hours_mask,
    double battery_capacity_wh,
    double initial_soc_percent,
    double constant_load_w,
    double charge_efficiency,
    double discharge_efficiency,
    double max_power_w
):
    """
    Ultra-hızlı batarya simülasyonu (C hızında)
    20-50x hızlanma beklenir
    """
    
    cdef int n = len(solar_power_normalized)
    cdef int i
    
    # C arrays (çok hızlı erişim)
    cdef cnp.ndarray[DTYPE_t, ndim=1] solar_power_w = np.zeros(n, dtype=np.float64)
    cdef cnp.ndarray[DTYPE_t, ndim=1] net_energy_wh = np.zeros(n, dtype=np.float64)
    cdef cnp.ndarray[DTYPE_t, ndim=1] soc_percent = np.zeros(n, dtype=np.float64)
    
    # Değişkenler
    cdef double battery_energy_wh = battery_capacity_wh * (initial_soc_percent / 100.0)
    cdef double solar_w, net_energy, load_energy_per_discharge
    
    # Sabit hesaplama (loop dışına çıkar)
    load_energy_per_discharge = constant_load_w / discharge_efficiency
    
    # Ana hesaplama loop'u (C hızında)
    for i in range(n):
        # Gece saatlerinde solar power = 0
        if night_hours_mask[i]:
            solar_w = 0.0
        else:
            solar_w = solar_power_normalized[i] * max_power_w
            
        solar_power_w[i] = solar_w
        
        # Net enerji hesapla
        net_energy = (solar_w * charge_efficiency) - load_energy_per_discharge
        net_energy_wh[i] = net_energy
        
        # Batarya seviyesi güncelle (clipping ile)
        battery_energy_wh = fmax(0.0, fmin(battery_capacity_wh, battery_energy_wh + net_energy))
        
        # SOC hesapla
        soc_percent[i] = (battery_energy_wh / battery_capacity_wh) * 100.0
    
    return solar_power_w, net_energy_wh, soc_percent

@cython.boundscheck(False)
@cython.wraparound(False)
def create_night_hours_mask(cnp.ndarray[cnp.int64_t, ndim=1] hours, 
                           int sunrise_hour, int sunset_hour):
    """Gece saatleri mask'ini C hızında oluştur"""
    cdef int n = len(hours)
    cdef cnp.ndarray[cnp.int64_t, ndim=1] mask = np.zeros(n, dtype=np.int64)
    cdef int i, hour
    
    for i in range(n):
        hour = hours[i]
        if hour > sunset_hour or hour < sunrise_hour:
            mask[i] = 1
        else:
            mask[i] = 0
    
    return mask.astype(bool)