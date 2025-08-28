#optized_forecaster.py
import time

import datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from prom import get_data_from_prometheus
from statsmodels.tsa.statespace.sarimax import SARIMAX
import warnings
warnings.filterwarnings('ignore')
from sklearn.preprocessing import MinMaxScaler

# Cython modüllerini import et
try:
    from battery_simulation import fast_battery_simulation, create_night_hours_mask
    from data_processing import fast_resample_hourly
    CYTHON_AVAILABLE = True
    #print("✅ Cython modülleri yüklendi - Ultra hız modu aktif!")
except ImportError:
    CYTHON_AVAILABLE = False
    #print("⚠️  Cython modülleri bulunamadı - Normal hız modu")


class OptimizedSolarPowerSARIMAXForecaster:
    def __init__(self, df=None,
                plot=False,
                detailed_summary=False, 
                use_cython=True,        
                metric = "mppt_values{sensor=\"panel gucu\"}", 
                prometheus_server_url = "http://10.67.67.22:9090",
                train_days = 7
                ):
        

        
        self.train_days = train_days
        self.plot = plot
        self.detailed_summary = detailed_summary
        self.metric = metric
        self.prometheus_server_url = prometheus_server_url

        self.df = df
        if self.df is not None:
            self.df = df.copy()
        if self.df is None:
            self.load_data()


        self.use_cython = use_cython and CYTHON_AVAILABLE
        
        self.prepare_data()


    def run(self,
         battery_capacity_wh=1500,
         initial_soc_percent=80,
         constant_load_w=100,
         charge_efficiency=0.9,
         discharge_efficiency=0.9,
        ):
        
        self.battery_capacity_wh=battery_capacity_wh
        self.initial_soc_percent=initial_soc_percent
        self.constant_load_w=constant_load_w
        self.charge_efficiency=charge_efficiency
        self.discharge_efficiency=discharge_efficiency


        train_hours = self.train_days * 24
        if len(self.hourly_data) < train_hours:
            print("HATA: Yeterli veri yok! En az {} saat gerekli.".format(train_hours + 24))
            return None

        # Son 7 gün + ertesi gün slice
        data_slice = self.hourly_data #self.hourly_data.iloc[-(train_hours):]

        self.forecast_on_slice(
            data_slice=data_slice,
        )  


        return self.simulation_result
    
    def load_data(self):
        #end_time = datetime.datetime.now()
        #start_time = end_time - datetime.timedelta(days=self.train_days+4)
        
        ######################
        date_string = "2025-08-12 00:00:00.00"
        format_string = "%Y-%m-%d %H:%M:%S.%f"
        start_time = datetime.datetime.strptime(date_string, format_string)
    #
        date_string = "2025-08-25 00:00:00.00"
        format_string = "%Y-%m-%d %H:%M:%S.%f"
        end_time = datetime.datetime.strptime(date_string, format_string)
        ##########################
        
        self.df = get_data_from_prometheus(
            prometheus_url=self.prometheus_server_url,
            metric_name=self.metric,
            start_time=start_time,
            end_time=end_time, 
            chunk_size=self.train_days+4
        )
        self.df["DC_POWER"] = self.df[self.metric]
        print(len(self.df["DC_POWER"]))
    def prepare_data(self):

        self.df['DATE_TIME'] = pd.to_datetime(self.df['DATE_TIME'])
        self.df = self.df.sort_values('DATE_TIME')

        self.df = self.df.set_index('DATE_TIME')
        self.max_power = self.df['DC_POWER'].max()


        cols_to_drop = ["PLANT_ID", "SOURCE_KEY", "AC_POWER", "TOTAL_YIELD"]
        existing_cols_to_drop = [col for col in cols_to_drop if col in self.df.columns]
        if existing_cols_to_drop:
            self.df.drop(existing_cols_to_drop, axis=1, inplace=True)

        scaler = MinMaxScaler(feature_range=(0, 1))
        self.df['DC_POWER'] = scaler.fit_transform(self.df[['DC_POWER']])
        #df = df.dropna().reset_index(drop=True)

        if self.use_cython:
            print("🚀 Cython ile Hızlı Veri Hazırlama...")
            timestamps_ns = self.df.index.values.astype(np.int64)
            dc_power_vals = self.df['DC_POWER'].values.astype(np.float64)

            res_ts_dc, res_vals_dc = fast_resample_hourly(timestamps_ns, dc_power_vals)
            
            index = pd.to_datetime(res_ts_dc, unit='ns')
            self.hourly_data = pd.DataFrame({'DC_POWER': res_vals_dc}, index=index)
            
        
        else:
            print("⚠️  Pandas ile Normal Veri Hazırlama...")
            # Normal pandas resampling
            self.hourly_data = self.df.resample('H').agg({
                'DC_POWER': 'mean',
            }).dropna()
        
        print(f"Saatlik veri hazırlandı: {len(self.hourly_data)} kayıt")
    
    def _simulate_battery_soc_optimized(self, history_data, predicted_dc_power_df):
        
        print(f"\n{'='*40}")
        if self.use_cython:
            print("AKÜ DOLULUK ORANI SİMÜLASYONU (CYTHON)")
        else:
            print("AKÜ DOLULUK ORANI SİMÜLASYONU")
        print(f"{'='*40}")
        
        # Dinamik gece saatleri hesaplama
        previous_day_data = history_data.iloc[-24:]
        production_hours = previous_day_data[previous_day_data['DC_POWER'] > 0.01]
        
        if not production_hours.empty:
            sunrise_hour = production_hours.index.hour.min()
            sunset_hour = production_hours.index.hour.max()
        else:
            sunrise_hour, sunset_hour = 7, 18

        # Veri hazırlama
        forecast_power = predicted_dc_power_df['Predicted_DC_POWER'].values
        forecast_index = predicted_dc_power_df.index
        
        history_power = history_data['DC_POWER'].values
        combined_power_source = np.concatenate([history_power, forecast_power])
        combined_index = history_data.index.append(forecast_index)
        
        if self.use_cython:
            # CYTHON İLE ULTRA HIZ HESAPLAMA
            start_time = time.time()

            # Gece saatleri mask'ini oluştur
            all_hours = combined_index.hour.values.astype(np.int64)
            night_hours_mask = create_night_hours_mask(all_hours, sunrise_hour, sunset_hour)
            
            # Ultra-hızlı batarya simülasyonu
            solar_power_w, net_energy_wh, soc_percent = fast_battery_simulation(
                combined_power_source.astype(np.float64),
                night_hours_mask.astype(np.int64),
                float(self.battery_capacity_wh),
                float(self.initial_soc_percent),
                float(self.constant_load_w),
                float(self.charge_efficiency),
                float(self.discharge_efficiency),
                float(self.max_power)
            )
            
            end_time = time.time()
            print(f"🚀 Cython simülasyon süresi: {end_time - start_time:.4f} saniye")
            
        else:
            # NORMAL PYTHON HESAPLAMA
            start_time = time.time()
            
            # Gece saatlerini sıfırla
            night_hours_mask = (combined_index.hour > sunset_hour) | (combined_index.hour < sunrise_hour)
            combined_power_source[night_hours_mask] = 0
            
            # Normal hesaplama
            solar_power_w = combined_power_source * self.max_power
            load_energy_wh = self.constant_load_w
            net_energy_wh = (solar_power_w * self.charge_efficiency) - (load_energy_wh / self.discharge_efficiency)
            
            # SOC hesaplama (loop)
            battery_energy_wh_array = np.zeros(len(net_energy_wh) + 1)
            battery_energy_wh_array[0] = self.battery_capacity_wh * (self.initial_soc_percent / 100.0)
            
            for i in range(len(net_energy_wh)):
                battery_energy_wh_array[i+1] = np.clip(
                    battery_energy_wh_array[i] + net_energy_wh[i], 0, self.battery_capacity_wh
                )
            
            soc_percent = (battery_energy_wh_array[1:] / self.battery_capacity_wh) * 100
            
            end_time = time.time()
            print(f"⚠️  Normal Python simülasyon süresi: {end_time - start_time:.4f} saniye")
        
        # DataFrame oluştur
        sim_df = pd.DataFrame({
            'SOC_Percent': soc_percent,
            'Solar_Power_W': solar_power_w,
            'Net_Energy_Wh': net_energy_wh
        }, index=combined_index)
        
        forecast_start_time = predicted_dc_power_df.index[0]
        forecast_data = sim_df.loc[forecast_start_time:].copy()

        if self.plot:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
            
            ax1.plot(sim_df.index, sim_df['Solar_Power_W'], label='Güneş Paneli Gücü (W)', color='orange')
            ax1.axhline(y=self.constant_load_w, color='gray', linestyle='--', label=f'Sabit Yük ({self.constant_load_w}W)')
            ax1.axvline(x=forecast_start_time, color='black', linestyle=':', label='Tahmin Başlangıcı')
            ax1.set_title('Enerji Üretimi ve Tüketimi', fontsize=14)
            ax1.set_ylabel('Güç (Watt)')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            ax2.plot(sim_df.index, sim_df['SOC_Percent'], 'g-', label='Akü SOC (%)', linewidth=3)
            ax2.axvline(x=forecast_start_time, color='black', linestyle=':', label='Tahmin Başlangıcı')
            ax2.axhline(y=20, color='red', linestyle='--', label='Kritik Seviye (%20)')
            ax2.fill_between(sim_df.index, 0, 20, color='red', alpha=0.1)
            
            forecast_soc = sim_df.loc[forecast_start_time:, 'SOC_Percent']
            min_soc = forecast_soc.min()
            min_soc_time = forecast_soc.idxmin()
            ax2.plot(min_soc_time, min_soc, 'ro', markersize=10, label=f'En Düşük Tahmin: {min_soc:.1f}%')
            ax2.set_title('Akü Doluluk Oranı Simülasyonu', fontsize=14)
            ax2.set_xlabel('Saat')
            ax2.set_ylabel('SOC (%)')
            ax2.set_ylim(0, 105)
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.savefig(f"battery_simulation_{np.random.randint(1e9)}.png")

        if not self.detailed_summary:
            min_soc_value = forecast_data['SOC_Percent'].min()
            status = "✅ GÜVENLİ"
            if min_soc_value < 15:
                status = "🚨 KRİTİK RİSK"
            elif min_soc_value < 30:
                status = "⚠️ DİKKATLİ OLUNMALI"
            
            return {
                "summary_type": "simple",
                "date": forecast_start_time.strftime('%Y-%m-%d'),
                "status": status,
                "min_soc": round(min_soc_value, 1)
            }
        
        else:
            # Detaylı Raporlama
            min_soc = forecast_data['SOC_Percent'].min()
            min_soc_time = forecast_data['SOC_Percent'].idxmin()
            max_soc = forecast_data['SOC_Percent'].max()
            max_soc_time = forecast_data['SOC_Percent'].idxmax()
            end_of_day_soc = forecast_data['SOC_Percent'].iloc[-1]
            
            # Tam dolum zamanı kontrolü
            time_to_full = None
            full_charge_events = forecast_data[forecast_data['SOC_Percent'] >= 99.9]
            if not full_charge_events.empty:
                time_to_full = full_charge_events.index[0].strftime('%H:%M')
            
            # Enerji hesaplamaları
            total_solar_energy = forecast_data['Solar_Power_W'].sum()
            total_load_energy = self.constant_load_w * 24
            net_battery_change_wh = forecast_data['Net_Energy_Wh'].sum()
            
            # Durum belirleme
            status = "✅ GÜVENLİ"
            if min_soc < 15:
                status = "🚨 KRİTİK RİSK"
            elif min_soc < 30:
                status = "⚠️ DİKKATLİ OLUNMALI"
            
            # 3 saatlik özet
            hourly_summary = forecast_data['SOC_Percent'].resample('3H').mean()
            hourly_data = []
            for timestamp, soc in hourly_summary.items():
                hourly_data.append({"time": timestamp.strftime('%H:%M'), "soc_percent": round(soc, 1)})
            
            # Eylem önerileri
            action_recommendations = []
            if status != "GÜVENLİ":
                if min_soc < 15:
                    action_recommendations.append("Yüksek Risk: Kritik yüklerin kapatılması gerekebilir.")
                elif min_soc < 30:
                    action_recommendations.append("Orta Risk: Enerji tasarrufu modu aktive edilmeli.")
            
            # Enerji durumu açıklaması
            energy_status_description = ""
            if net_battery_change_wh > 0:
                energy_status_description = "Gün sonunda akü daha dolu olacak"
            else:
                energy_status_description = "Gün sonunda akü daha boş olacak"
            
            return {
                "summary_type": "detailed",
                "date": forecast_start_time.strftime('%Y-%m-%d'),
                "general_status": status,
                "battery_performance": {
                    "initial_soc": round(self.initial_soc_percent, 1),
                    "min_soc": round(min_soc, 1),
                    "min_soc_time": min_soc_time.strftime('%H:%M'),
                    "max_soc": round(max_soc, 1),
                    "max_soc_time": max_soc_time.strftime('%H:%M'),
                    "end_of_day_soc": round(end_of_day_soc, 1),
                    "time_to_full": time_to_full,
                    "full_charge_expected": time_to_full is not None
                },
                "energy_balance": {
                    "total_production_kwh": round(total_solar_energy / 1000, 2),
                    "total_consumption_kwh": round(total_load_energy / 1000, 2),
                    "net_battery_change_wh": round(net_battery_change_wh, 1),
                    "status_description": energy_status_description
                },
                "hourly_summary": {
                    "interval": "3_hours",
                    "data": hourly_data
                },
                "action_recommendations": action_recommendations,
                "timestamp": datetime.datetime.now().isoformat()
            }

        
    def forecast_on_slice(self, data_slice):
        order=(1,1,1)
        seasonal_order=(1,0,1,24)
        
        train_hours = self.train_days * 24
        min_test_hours = 24  # At least 1 day for testing
        
        # Check if we have enough data
        if len(data_slice) < train_hours + min_test_hours:
            print(f"WARNING: Not enough data! Have {len(data_slice)} rows but need at least {train_hours + min_test_hours}")
            self.simulation_result = None
            return
        
        train_data = data_slice.iloc[:train_hours]
        test_data = data_slice.iloc[train_hours:]
        
        print(f"Train data length: {len(train_data)}")
        print(f"Test data length: {len(test_data)}")
        
        try:
            print(train_data['DC_POWER'])

            model = SARIMAX(
                train_data['DC_POWER'],
                order=order, seasonal_order=seasonal_order
            )
            
            fitted_model = model.fit(disp=False, solver='powell')
            
            forecast = fitted_model.forecast(steps=len(test_data))
            forecast = np.clip(forecast, 0, 1)
            
            forecast_df = pd.DataFrame({
                'Predicted_DC_POWER': forecast.values
            }, index=forecast.index)

            history_start_index = len(train_data) - (3 * 24)
            history_data = train_data.iloc[history_start_index:]
            
            self.simulation_result = self._simulate_battery_soc_optimized(
                history_data=history_data,
                predicted_dc_power_df=forecast_df
                )
            
        except Exception as e:
            raise e
            #print(f"Model veya simülasyon hatası: {str(e)}")

