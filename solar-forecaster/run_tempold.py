import logging
import uuid
from typing import Optional, Dict, Any
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import BadRequest
from dotenv import load_dotenv, dotenv_values
import pandas as pd
from pathlib import Path

if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('/app/logs/api.log'),
            logging.StreamHandler()
        ]
    )

logger = logging.getLogger(__name__)

class DockerServiceAPI:
    """Docker servis olarak çalışan API sınıfı"""
    
    def __init__(self):
        self.app = Flask(__name__)
        self.app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit
        self.upload_folder = Path('/app/uploads')
        self.upload_folder.mkdir(exist_ok=True)
        
        # Geçici session depolama
        self.active_sessions = {}
        
        self.setup_routes()
    
    def setup_routes(self):
        """API route'larını tanımlar"""
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Sağlık kontrolü"""
            return jsonify({
                "status": "healthy",
                "service": "solar-forecaster",
                "timestamp": pd.Timestamp.now().isoformat(),
                "version": "2.0"
            })
        
        @self.app.route('/upload-env', methods=['POST'])
        def upload_env_file():
            """
            .env dosyası yükleme endpoint'i
            Multipart form data ile dosya kabul eder
            """
            try:
                if 'env_file' not in request.files:
                    return jsonify({
                        "status": "error",
                        "message": "No env_file provided in request"
                    }), 400
                
                file = request.files['env_file']
                if file.filename == '':
                    return jsonify({
                        "status": "error",
                        "message": "No file selected"
                    }), 400
                
                if not file.filename.endswith('.env'):
                    return jsonify({
                        "status": "error",
                        "message": "File must have .env extension"
                    }), 400
                
                # Güvenli dosya adı ve session ID oluştur
                session_id = str(uuid.uuid4())
                filename = secure_filename(f"{session_id}_{file.filename}")
                file_path = self.upload_folder / filename
                
                # Dosyayı kaydet
                file.save(str(file_path))
                
                # .env dosyasını doğrula ve parse et
                try:
                    env_vars = dotenv_values(str(file_path))
                    
                    # Boş veya geçersiz dosya kontrolü
                    if not env_vars:
                        file_path.unlink()  # Dosyayı sil
                        return jsonify({
                            "status": "error",
                            "message": "Empty or invalid .env file"
                        }), 400
                    
                    # Session'ı kaydet
                    self.active_sessions[session_id] = {
                        "file_path": str(file_path),
                        "env_vars": env_vars,
                        "upload_time": pd.Timestamp.now().isoformat(),
                        "original_filename": file.filename
                    }
                    
                    logger.info(f"Env file uploaded successfully. Session: {session_id}")
                    
                    return jsonify({
                        "status": "success",
                        "message": "Environment file uploaded successfully",
                        "session_id": session_id,
                        "variables_count": len(env_vars),
                        "variables": list(env_vars.keys())  # Sadece key'leri döndür
                    })
                    
                except Exception as e:
                    if file_path.exists():
                        file_path.unlink()
                    raise ValueError(f"Invalid .env file format: {e}")
                    
            except Exception as e:
                logger.error(f"Error uploading env file: {e}")
                return jsonify({
                    "status": "error",
                    "message": f"Upload failed: {str(e)}"
                }), 500
        
        @self.app.route('/run-with-env/<session_id>', methods=['POST'])
        def run_forecast_with_env(session_id):
            """
            Session ID ile tahmin çalıştırma
            Ek parametreler JSON ile gönderilebilir (override için)
            """
            try:
                # Session kontrolü
                if session_id not in self.active_sessions:
                    return jsonify({
                        "status": "error",
                        "message": "Invalid session_id or session expired"
                    }), 404
                
                session_data = self.active_sessions[session_id]
                env_vars = session_data['env_vars'].copy()
                
                # Request'ten gelen ek/override parametreler
                additional_params = request.get_json() or {}
                
                # Override parametrelerini ekle
                env_vars.update(additional_params)
                
                logger.info(f"Running forecast with session {session_id}, {len(env_vars)} variables")
                
                # Forecaster'ı çalıştır
                result = self.run_forecaster_with_env(env_vars)
                
                return jsonify({
                    "status": "success",
                    "result": result,
                    "session_id": session_id,
                    "timestamp": pd.Timestamp.now().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Error running forecast with env: {e}")
                return jsonify({
                    "status": "error",
                    "message": str(e)
                }), 500
        
        @self.app.route('/run', methods=['POST'])
        def run_forecast_json():
            """
            Geleneksel JSON parametreleri ile tahmin çalıştırma
            Geriye uyumluluk için
            """
            try:
                params = request.get_json() or {}
                logger.info(f"Running forecast with JSON parameters: {len(params)} variables")
                
                result = self.run_forecaster_with_env(params)
                
                return jsonify({
                    "status": "success",
                    "result": result,
                    "timestamp": pd.Timestamp.now().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Error running forecast: {e}")
                return jsonify({
                    "status": "error",
                    "message": str(e)
                }), 500
        
        @self.app.route('/sessions', methods=['GET'])
        def list_sessions():
            """Aktif session'ları listeler"""
            sessions = {}
            for sid, data in self.active_sessions.items():
                sessions[sid] = {
                    "original_filename": data['original_filename'],
                    "upload_time": data['upload_time'],
                    "variables_count": len(data['env_vars'])
                }
            
            return jsonify({
                "status": "success",
                "active_sessions": len(sessions),
                "sessions": sessions
            })
        
        @self.app.route('/sessions/<session_id>', methods=['DELETE'])
        def delete_session(session_id):
            """Session'ı ve ilgili dosyayı siler"""
            try:
                if session_id not in self.active_sessions:
                    return jsonify({
                        "status": "error",
                        "message": "Session not found"
                    }), 404
                
                session_data = self.active_sessions[session_id]
                
                # Dosyayı sil
                file_path = Path(session_data['file_path'])
                if file_path.exists():
                    file_path.unlink()
                
                # Session'ı sil
                del self.active_sessions[session_id]
                
                logger.info(f"Session {session_id} deleted")
                
                return jsonify({
                    "status": "success",
                    "message": "Session deleted successfully"
                })
                
            except Exception as e:
                logger.error(f"Error deleting session: {e}")
                return jsonify({
                    "status": "error",
                    "message": str(e)
                }), 500
        
        @self.app.route('/sample-env', methods=['GET'])
        def get_sample_env():
            sample_content = '''
                            PROMETHEUS_URL=http://localhost:9090
                            METRIC_NAME=mppt_values{sensor="panel gucu"}
                            TRAIN_DAYS=7
                            BATTERY_CAPACITY_WH=1500.0
                            INITIAL_SOC_PERCENT=80.0
                            CONSTANT_LOAD_W=100.0
                            CHARGE_EFFICIENCY=0.9
                            DISCHARGE_EFFICIENCY=0.9
                            DETAILED_SUMMARY=true
                            USE_CYTHON=true
                            # DATA_PATH=/path/to/data.csv
                            '''
            
            return jsonify({
                "status": "success",
                "sample_env_content": sample_content,
                "description": "Copy this content to create your .env file"
            })
        
        @self.app.errorhandler(413)
        def file_too_large(e):
            return jsonify({
                "status": "error",
                "message": "File too large. Maximum size: 16MB"
            }), 413
    
    def run_forecaster_with_env(self, env_vars: Dict[str, Any]) -> Dict[str, Any]:
        """
        Environment variables ile forecaster'ı çalıştırır
        
        Args:
            env_vars: Environment variables dictionary
            
        Returns:
            Simulation result dictionary
        """
        # Varsayılan değerler
        defaults = {
            "PROMETHEUS_URL": "http://localhost:9090",
            "METRIC_NAME": "mppt_values{sensor=\"panel gucu\"}",
            "TRAIN_DAYS": 5,
            "BATTERY_CAPACITY_WH": 1500.0,
            "INITIAL_SOC_PERCENT": 80.0,
            "CONSTANT_LOAD_W": 100.0,
            "CHARGE_EFFICIENCY": 0.9,
            "DISCHARGE_EFFICIENCY": 0.9,
            "DETAILED_SUMMARY": False,
            "USE_CYTHON": True,
            "DATA_PATH": None
        }
        
        # Environment variables'ı merge et
        config = defaults.copy()
        config.update(env_vars)
        
        # Tip dönüştürmeleri
        config['TRAIN_DAYS'] = int(config['TRAIN_DAYS'])
        config['BATTERY_CAPACITY_WH'] = float(config['BATTERY_CAPACITY_WH'])
        config['INITIAL_SOC_PERCENT'] = float(config['INITIAL_SOC_PERCENT'])
        config['CONSTANT_LOAD_W'] = float(config['CONSTANT_LOAD_W'])
        config['CHARGE_EFFICIENCY'] = float(config['CHARGE_EFFICIENCY'])
        config['DISCHARGE_EFFICIENCY'] = float(config['DISCHARGE_EFFICIENCY'])
        config['DETAILED_SUMMARY'] = str(config['DETAILED_SUMMARY']).lower() in ('true', '1', 'yes', 'on')
        config['USE_CYTHON'] = str(config['USE_CYTHON']).lower() in ('true', '1', 'yes', 'on')
        
        # Veri dosyasını yükle
        df = None
        if config['DATA_PATH'] and config['DATA_PATH'] != 'None':
            try:
                df = pd.read_csv(config['DATA_PATH'])
                logger.info(f"Data loaded from: {config['DATA_PATH']}")
            except Exception as e:
                logger.warning(f"Could not load data file: {e}")
        

        try:
            from optimized_forecaster import OptimizedSolarPowerSARIMAXForecaster
            
            forecaster = OptimizedSolarPowerSARIMAXForecaster(
                df=df,
                plot=False,
                detailed_summary=config['DETAILED_SUMMARY'],
                use_cython=config['USE_CYTHON'],
                metric=config['METRIC_NAME'],
                prometheus_server_url=config['PROMETHEUS_URL'],
                train_days=config['TRAIN_DAYS']
            )
            
            if forecaster.df is None:
                raise ValueError("No data could be loaded")

            
            if forecaster.hourly_data is None or forecaster.hourly_data.empty:
                raise ValueError("No hourly data available for forecasting")
            
            result = forecaster.run(
                battery_capacity_wh=config['BATTERY_CAPACITY_WH'],
                initial_soc_percent=config['INITIAL_SOC_PERCENT'],
                constant_load_w=config['CONSTANT_LOAD_W'],
                charge_efficiency=config['CHARGE_EFFICIENCY'],
                discharge_efficiency=config['DISCHARGE_EFFICIENCY']
            )
            
            if result is None:
                raise ValueError("Simulation failed to produce results")
            
            return result
            
        except ImportError:
            # Mock result for testing
            return {
                "summary_type": "detailed",
                "date": pd.Timestamp.now().strftime('%Y-%m-%d'),
                "general_status": "✅ GÜVENLİ",
                "message": "Mock result - replace with actual forecaster",
                "config_used": config
            }
    
    def run(self, host='0.0.0.0', port=4545, debug=False):
        """API sunucusunu başlatır"""
        logger.info(f"Starting Docker Service API on {host}:{port}")
        logger.info(f"Upload folder: {self.upload_folder}")
        
        # Log dizinini oluştur
        Path('/app/logs').mkdir(exist_ok=True)
        
        self.app.run(host=host, port=port, debug=debug)

def main():
    """Ana fonksiyon"""
    api = DockerServiceAPI()
    api.run()

if __name__ == "__main__":
    main()


"""
POST /upload-env              # .env dosyası yükle
POST /run-with-env/<session>  # Session ile tahmin çalıştır  
POST /run                     # Geleneksel JSON (geriye uyumlu)
GET  /health                  # Sağlık kontrolü
GET  /sessions               # Aktif session'ları listele
DELETE /sessions/<session>   # Session sil
GET  /sample-env            # Örnek .env içeriği
"""