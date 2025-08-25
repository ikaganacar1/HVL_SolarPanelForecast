import logging
import uuid
from typing import Optional, Dict, Any
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify
from werkzeug.exceptions import BadRequest
from dotenv import dotenv_values
import pandas as pd
from pathlib import Path
from flasgger import Swagger

# Kendi modüllerinizi import edin
from optimized_forecaster import OptimizedSolarPowerSARIMAXForecaster

# Sadece root logger'da handler yoksa yapılandırarak çift loglamayı önle
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
        
        # --- SWAGGER YAPILANDIRMASI ---
        self.app.config['SWAGGER'] = {
            'title': 'Solar Power Forecaster API',
            'uiversion': 3,
            'version': '2.2.0',
            'description': 'Güneş enerjisi üretimi tahmini ve akü simülasyonu yapan API servisi. Oturum yönetimi ve yardımcı araçlar içerir.'
        }
        self.swagger = Swagger(self.app)
        logger.info("✅ Swagger UI başarıyla başlatıldı. Arayüze /apidocs adresinden ulaşabilirsiniz.")
        
        self.upload_folder = Path('/app/uploads')
        self.upload_folder.mkdir(exist_ok=True)
        
        # Geçici session depolama
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        
        self.setup_routes()
    
    def setup_routes(self):
        """API route'larını tanımlar"""
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """
            API Sağlık Durumu Kontrolü
            Servisin ayakta ve çalışır durumda olup olmadığını kontrol eder.
            ---
            tags:
              - Monitoring
            responses:
              200:
                description: Servis sağlıklı çalışıyor.
                schema:
                  type: object
                  properties:
                    status:
                      type: string
                      example: healthy
                    service:
                      type: string
                      example: solar-forecaster
            """
            return jsonify({
                "status": "healthy",
                "service": "solar-forecaster",
                "timestamp": pd.Timestamp.now().isoformat(),
                "version": "2.2"
            })
        
        @self.app.route('/sessions', methods=['GET'])
        def list_sessions():
            """
            Aktif tahmin oturumlarını listeler.
            Mevcut olarak sunucuda bulunan tüm aktif oturumları ve temel bilgilerini döndürür.
            ---
            tags:
              - Sessions
            responses:
              200:
                description: Aktif oturumların listesi başarıyla döndürüldü.
                schema:
                  type: object
                  properties:
                    status:
                      type: string
                      example: success
                    active_sessions:
                      type: integer
                      example: 2
                    sessions:
                      type: object
                      example: {
                        "session-id-1": {
                          "original_filename": "config.env",
                          "upload_time": "2025-08-19T12:30:00.123Z",
                          "variables_count": 10
                        }
                      }
            """
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
            """
            Belirtilen bir tahmin oturumunu ve ilgili dosyaları siler.
            ---
            tags:
              - Sessions
            parameters:
              - name: session_id
                in: path
                type: string
                required: true
                description: Silinecek oturumun ID'si.
            responses:
              200:
                description: Oturum başarıyla silindi.
              404:
                description: Belirtilen oturum ID'si bulunamadı.
              500:
                description: Oturum silinirken bir sunucu hatası oluştu.
            """
            try:
                if session_id not in self.active_sessions:
                    return jsonify({"status": "error", "message": "Session not found"}), 404
                
                session_data = self.active_sessions.pop(session_id)
                
                file_path = Path(session_data['file_path'])
                if file_path.exists():
                    file_path.unlink()
                
                logger.info(f"Session {session_id} deleted")
                
                return jsonify({"status": "success", "message": "Session deleted successfully"})
                
            except Exception as e:
                logger.error(f"Error deleting session {session_id}: {e}", exc_info=True)
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/sample-env', methods=['GET'])
        def get_sample_env():
            """
            Örnek bir .env dosyasının içeriğini döndürür.
            Kullanıcıların kendi .env dosyalarını oluşturmalarına yardımcı olmak için bir şablon sunar.
            ---
            tags:
              - Helper
            responses:
              200:
                description: Örnek .env içeriği başarıyla döndürüldü.
                schema:
                  type: object
                  properties:
                    status:
                      type: string
                      example: success
                    sample_env_content:
                      type: string
                    description:
                      type: string
            """
            sample_content = (
                "PROMETHEUS_URL=http://localhost:9090\n"
                "METRIC_NAME=mppt_values{sensor=\"panel gucu\"}\n"
                "TRAIN_DAYS=7\n"
                "BATTERY_CAPACITY_WH=1500.0\n"
                "INITIAL_SOC_PERCENT=80.0\n"
                "CONSTANT_LOAD_W=100.0\n"
                "CHARGE_EFFICIENCY=0.9\n"
                "DISCHARGE_EFFICIENCY=0.9\n"
                "DETAILED_SUMMARY=true\n"
                "USE_CYTHON=true\n"
            )
            return jsonify({
                "status": "success",
                "sample_env_content": sample_content,
                "description": "Copy this content to create your .env file"
            })
        
        @self.app.errorhandler(413)
        def file_too_large(e):
            """Dosya boyutu aşıldığında otomatik hata yanıtı döner."""
            return jsonify({"status": "error", "message": "File too large. Maximum size: 16MB"}), 413

        @self.app.route('/upload-env', methods=['POST'])
        def upload_env_file():
            """
            .env dosyası yükleyerek yeni bir tahmin oturumu başlatır.
            Bu endpoint üzerinden yüklenen .env dosyası ile bir session_id alınır.
            ---
            tags:
              - Forecaster
            consumes:
              - multipart/form-data
            parameters:
              - name: env_file
                in: formData
                type: file
                required: true
                description: Tahmin parametrelerini içeren .env dosyası.
            responses:
              200:
                description: Dosya başarıyla yüklendi ve oturum oluşturuldu.
              400:
                description: Hatalı istek (dosya eksik, format yanlış vb.).
              413:
                description: Dosya boyutu 16MB limitini aşıyor.
            """
            try:
                if 'env_file' not in request.files:
                    return jsonify({"status": "error", "message": "No env_file provided in request"}), 400
                
                file = request.files['env_file']
                if not file or not file.filename:
                    return jsonify({"status": "error", "message": "No file selected"}), 400
                
                if not file.filename.endswith('.env'):
                    return jsonify({"status": "error", "message": "File must have .env extension"}), 400
                
                session_id = str(uuid.uuid4())
                filename = secure_filename(f"{session_id}_{file.filename}")
                file_path = self.upload_folder / filename
                
                file.save(str(file_path))
                
                env_vars = dotenv_values(str(file_path))
                if not env_vars:
                    file_path.unlink()
                    return jsonify({"status": "error", "message": "Empty or invalid .env file"}), 400
                
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
                    "variables": list(env_vars.keys())
                })
                    
            except Exception as e:
                logger.error(f"Error uploading env file: {e}", exc_info=True)
                return jsonify({"status": "error", "message": f"Upload failed: {str(e)}"}), 500
        
        @self.app.route('/run-with-env/<session_id>', methods=['POST'])
        def run_forecast_with_env(session_id):
            """
            Daha önce yüklenmiş .env dosyası ile tahmin çalıştırır.
            Oluşturulmuş bir oturum ID'si kullanarak tahmin işlemini tetikler.
            ---
            tags:
              - Forecaster
            parameters:
              - name: session_id
                in: path
                type: string
                required: true
                description: /upload-env endpoint'inden alınan oturum ID'si.
              - name: body
                in: body
                description: .env dosyasındaki değerleri geçici olarak ezmek için kullanılan JSON objesi.
                schema:
                  type: object
                  example: {"CONSTANT_LOAD_W": 150.0, "DETAILED_SUMMARY": "false"}
            responses:
              200:
                description: Tahmin başarıyla tamamlandı.
              404:
                description: Belirtilen session_id bulunamadı.
              500:
                description: Tahmin sırasında bir hata oluştu.
            """
            try:
                if session_id not in self.active_sessions:
                    return jsonify({"status": "error", "message": "Invalid session_id or session expired"}), 404
                
                session_data = self.active_sessions[session_id]
                env_vars = session_data['env_vars'].copy()
                
                additional_params = request.get_json() or {}
                env_vars.update(additional_params)
                
                logger.info(f"Running forecast with session {session_id}, {len(env_vars)} variables")
                result = self.run_forecaster_with_env(env_vars)
                
                return jsonify({
                    "status": "success",
                    "result": result,
                    "session_id": session_id,
                    "timestamp": pd.Timestamp.now().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Error running forecast with env: {e}", exc_info=True)
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/run', methods=['POST'])
        def run_forecast_json():
            """
            JSON objesi ile doğrudan tahmin çalıştırır.
            Tüm tahmin parametrelerini bir JSON objesi olarak alarak tahmin işlemini gerçekleştirir.
            ---
            tags:
              - Forecaster
            parameters:
              - name: body
                in: body
                required: true
                schema:
                  id: ForecastInput
                  required:
                    - PROMETHEUS_URL
                    - METRIC_NAME
                  properties:
                    PROMETHEUS_URL:
                      type: string
                      example: 'http://10.67.67.22:9090'
                    METRIC_NAME:
                      type: string
                      example: 'mppt_values{sensor="panel gucu"}'
                    TRAIN_DAYS:
                      type: integer
                      example: 7
                    BATTERY_CAPACITY_WH:
                      type: number
                      example: 1500.0
                    INITIAL_SOC_PERCENT:
                      type: number
                      example: 80.0
                    CONSTANT_LOAD_W:
                      type: number
                      example: 100.0
                    CHARGE_EFFICIENCY:
                      type: number
                      example: 0.9
                    DISCHARGE_EFFICIENCY:
                      type: number
                      example: 0.9
                    DETAILED_SUMMARY:
                      type: boolean
                      example: true
                    USE_CYTHON:
                      type: boolean
                      example: true
            responses:
              200:
                description: Tahmin başarıyla tamamlandı.
              400:
                description: Hatalı veya eksik JSON.
              500:
                description: Tahmin sırasında bir hata oluştu.
            """
            try:
                params = request.get_json()
                if not params:
                    raise BadRequest("Request body must be a valid JSON.")
                
                logger.info(f"Running forecast with JSON parameters: {len(params)} variables")
                result = self.run_forecaster_with_env(params)
                
                if result is None:
                    raise Exception("Forecast simulation failed to produce results.")

                return jsonify({
                    "status": "success",
                    "result": result,
                    "timestamp": pd.Timestamp.now().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Error running forecast: {e}", exc_info=True)
                return jsonify({"status": "error", "message": str(e)}), 500
    
    def run_forecaster_with_env(self, env_vars: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Gelen parametrelerle forecaster'ı çalıştırır ve sonucu döner"""
        
        # --- YENİ: ZORUNLU PARAMETRE KONTROLÜ ---
        required_params = ['PROMETHEUS_URL', 'METRIC_NAME']
        missing_params = [p for p in required_params if not env_vars.get(p)]
        if missing_params:
            raise BadRequest(f"Missing required parameters: {', '.join(missing_params)}")
        
        # Gelen string değerleri doğru tiplere dönüştür
        train_days = int(env_vars.get('TRAIN_DAYS', 7))
        battery_capacity_wh = float(env_vars.get('BATTERY_CAPACITY_WH', 1500.0))
        initial_soc_percent = float(env_vars.get('INITIAL_SOC_PERCENT', 80.0))
        constant_load_w = float(env_vars.get('CONSTANT_LOAD_W', 100.0))
        charge_efficiency = float(env_vars.get('CHARGE_EFFICIENCY', 0.9))
        discharge_efficiency = float(env_vars.get('DISCHARGE_EFFICIENCY', 0.9))
        detailed_summary = str(env_vars.get('DETAILED_SUMMARY', 'true')).lower() in ['true', '1', 't']
        use_cython = str(env_vars.get('USE_CYTHON', 'true')).lower() in ['true', '1', 't']
        
        forecaster = OptimizedSolarPowerSARIMAXForecaster(
            prometheus_server_url=env_vars.get('PROMETHEUS_URL'),
            metric=env_vars.get('METRIC_NAME'),
            train_days=train_days,
            detailed_summary=detailed_summary,
            use_cython=use_cython
        )
        
        simulation_result = forecaster.run(
            battery_capacity_wh=battery_capacity_wh,
            initial_soc_percent=initial_soc_percent,
            constant_load_w=constant_load_w,
            charge_efficiency=charge_efficiency,
            discharge_efficiency=discharge_efficiency
        )
        
        return simulation_result

if __name__ == '__main__':
    api = DockerServiceAPI()
    api.app.run(host='0.0.0.0', port=4545, debug=False)
