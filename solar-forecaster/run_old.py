# run.py

import os
from dotenv import load_dotenv
import pandas as pd
from optimized_forecaster import OptimizedSolarPowerSARIMAXForecaster
import time

# .env dosyasındaki değişkenleri yükle
load_dotenv()

def get_env_variable(var_name, default_value, var_type=str):
    """Ortam değişkenini okur, yoksa varsayılanı kullanır ve tip dönüşümü yapar."""
    value = os.getenv(var_name, str(default_value))
    try:
        if var_type == bool:
            return value.lower() in ['true', '1', 't', 'y', 'yes']
        if value in ["None" , "none", "NONE"]:
            return None
        
        return var_type(value)

    except ValueError:
        print(f"UYARI: '{var_name}' için geçersiz değer '{value}'. Varsayılan '{default_value}' kullanılıyor.")
        return default_value

def run_app():
    prometheus_url = get_env_variable("PROMETHEUS_URL", "http://localhost:9090")
    metric = get_env_variable("METRIC_NAME", "mppt_values{sensor=\"panel gucu\"}")
    train_days = get_env_variable("TRAIN_DAYS", 7, int)
    battery_capacity = get_env_variable("BATTERY_CAPACITY_WH", 1500, float)
    initial_soc = get_env_variable("INITIAL_SOC_PERCENT", 80, float)
    constant_load = get_env_variable("CONSTANT_LOAD_W", 100, float)
    charge_eff = get_env_variable("CHARGE_EFFICIENCY", 0.9, float)
    discharge_eff = get_env_variable("DISCHARGE_EFFICIENCY", 0.9, float)
    plot = get_env_variable("PLOT_RESULTS", False, bool)
    detailed_summary = get_env_variable("DETAILED_SUMMARY", False, bool)
    use_cython = get_env_variable("USE_CYTHON", True, bool)
    data_path = get_env_variable("DATA_PATH", None)
    
    df = None
    if data_path is not None:
        try:
            df = pd.read_csv(data_path)
        except FileNotFoundError:
            print(f"HATA: '{data_path}' dosyası bulunamadı..")
            return
    
    
    try:
        start_time = time.time()
        
        forecaster = OptimizedSolarPowerSARIMAXForecaster(
            df=df,
            plot=plot,
            detailed_summary=detailed_summary,
            use_cython=use_cython,
            metric=metric,
            prometheus_server_url=prometheus_url,
            train_days=train_days
        )
        if forecaster.df is None:
            print("HATA: Veri kaynağı (CSV veya Prometheus) yüklenemedi. İşlem durduruluyor.")
            
        if forecaster.hourly_data is not None and not forecaster.hourly_data.empty:
            forecaster.run(
                battery_capacity_wh=battery_capacity,
                initial_soc_percent=initial_soc,
                constant_load_w=constant_load,
                charge_efficiency=charge_eff,
                discharge_efficiency=discharge_eff,
            )
        else:
            print("HATA: Tahmin için yeterli veri hazırlanamadı.")
            
        elapsed_time = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"Tüm İşlem Tamamlandı. Toplam Süre: {elapsed_time:.3f} saniye")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"Beklenmedik bir hata oluştu: {e}")

def run_api():
    from flask import Flask, request, jsonify
    app = Flask(__name__)

    @app.route("/run", methods=["POST"])
    def run_forecast():
        params = request.json or {}
        print(f"API çağrısı ile gelen parametreler: {params}")

        # Ortam değişkenlerini güncelle (sadece bu process için)
        for key, value in params.items():
            os.environ[key] = str(value)

        # Ortamdan parametreleri oku
        prometheus_url = get_env_variable("PROMETHEUS_URL", "http://localhost:9090")
        metric = get_env_variable("METRIC_NAME", "mppt_values{sensor=\"panel gucu\"}")
        train_days = get_env_variable("TRAIN_DAYS", 7, int)
        battery_capacity = get_env_variable("BATTERY_CAPACITY_WH", 1500, float)
        initial_soc = get_env_variable("INITIAL_SOC_PERCENT", 80, float)
        constant_load = get_env_variable("CONSTANT_LOAD_W", 100, float)
        charge_eff = get_env_variable("CHARGE_EFFICIENCY", 0.9, float)
        discharge_eff = get_env_variable("DISCHARGE_EFFICIENCY", 0.9, float)
        detailed_summary = get_env_variable("DETAILED_SUMMARY", False, bool)
        use_cython = get_env_variable("USE_CYTHON", True, bool)
        data_path = get_env_variable("DATA_PATH", None)

        df = None
        if data_path is not None:
            try:
                df = pd.read_csv(data_path)
            except FileNotFoundError:
                return jsonify({"status": "error", "message": f"'{data_path}' not found."}), 400

        try:
            forecaster = OptimizedSolarPowerSARIMAXForecaster(
                df=df,
                plot=False,
                detailed_summary=detailed_summary,
                use_cython=use_cython,
                metric=metric,
                prometheus_server_url=prometheus_url,
                train_days=train_days
            )
            if forecaster.df is None:
                return jsonify({"status": "error", "message": "No data loaded."}), 400

            if forecaster.hourly_data is not None and not forecaster.hourly_data.empty:
                simulation_result = forecaster.run(
                    battery_capacity_wh=battery_capacity,
                    initial_soc_percent=initial_soc,
                    constant_load_w=constant_load,
                    charge_efficiency=charge_eff,
                    discharge_efficiency=discharge_eff,
                )
                if simulation_result is not None:
                    return jsonify({"status": "ok", "result": simulation_result})
                else:
                    return jsonify({"status": "error", "message": "Simulation failed."}), 500
            else:
                return jsonify({"status": "error", "message": "No data for forecast."}), 400

        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    app.run(host="0.0.0.0", port=4545)

# Ana giriş noktası
if __name__ == "__main__":
    import sys
    print(len(sys.argv), sys.argv)
    if len(sys.argv) > 1 and sys.argv[1] == "api":
        run_api()


