from prometheus_api_client import PrometheusConnect
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt


def get_data_from_prometheus(prometheus_url, metric_name, start_time, end_time, chunk_size=7):

    print(f"\nPrometheus'tan '{metric_name}' metriği çekiliyor...")
    print(f"Zaman aralığı: {start_time} -> {end_time}")

    try:
        prom = PrometheusConnect(url=prometheus_url, disable_ssl=True)
        
        metric_data = prom.get_metric_range_data(
            metric_name=metric_name, 
            start_time=start_time,
            end_time=end_time,
            chunk_size=timedelta(days=chunk_size),
            store_locally=False,
        )

        if not metric_data:
            print("UYARI: Prometheus'tan veri alınamadı.")
            return None

        data = metric_data[0] 
        df = pd.DataFrame(data['values'], columns=['DATE_TIME', 'value'])
        df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], unit='s')
        df['value'] = pd.to_numeric(df['value'])
        
        df.rename(columns={'value': metric_name}, inplace=True)
        print(f"Başarıyla {len(df)} kayıt çekildi.")
        return df

    except Exception as e:
        print(f"Prometheus hatası: {e}")
        return None

def main():
    prometheus_server_url = "http://10.67.67.22:9090"

    panel_gucu_metric = "mppt_values{sensor=\"panel gucu\"}" 

    #end_time = datetime.now()
    #start_time = end_time - timedelta(days=7)

    ######################
    date_string = "2025-08-01 15:00:49.345556"
    format_string = "%Y-%m-%d %H:%M:%S.%f"
    start_time = datetime.strptime(date_string, format_string)
#
    date_string = "2025-09-1 00:00:00.00"
    format_string = "%Y-%m-%d %H:%M:%S.%f"
    end_time = datetime.strptime(date_string, format_string)
    ##########################
    
    df_panel_gucu = get_data_from_prometheus(
        prometheus_url=prometheus_server_url,
        metric_name=panel_gucu_metric,
        start_time=start_time,
        end_time=end_time,
        chunk_size=7
    )
    if df_panel_gucu is not None:

        df_panel_gucu.set_index('DATE_TIME').plot(title='Panel Gücü (Son 7 Gün)')
        plt.show()

#main()