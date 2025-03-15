import threading
import os
import time
import requests
from flask import Flask
from services.mmr_processor import processar_mmr_todos_jogadores
from database.mongodb_client import connect_db, create_collections
from bot.discord_bot import ArenaBot
from config import DISCORD_TOKEN, MMR_UPDATE_INTERVAL
from logs.logger import Logger
from services.scheduler import TaskScheduler

# Create Flask app
app = Flask(__name__)

@app.route('/')
def home():
    return 'Arena Ranking Bot is running!'

@app.route('/health')
def health_check():
    return 'OK', 200

def run_discord_bot(db, logger):
    """Run the Discord bot in a separate thread"""
    logger.info("Inicializando o bot Discord...")
    bot = ArenaBot()
    logger.info("Executando o bot Discord...")
    bot.run(DISCORD_TOKEN)

def keep_alive(logger):
    """Ping the health endpoint to keep the server active"""
    app_url = os.environ.get('APP_URL', 'http://localhost:5000')
    logger.info(f"Iniciando serviço keep-alive para {app_url}")
    
    while True:
        try:
            response = requests.get(f"{app_url}/health", timeout=10)
            logger.info(f"Keep-alive ping: status {response.status_code}")
        except Exception as e:
            logger.error(f"Erro no keep-alive ping: {str(e)}")
        time.sleep(300)  # Ping every 5 minutes

def bot_watchdog(initial_thread, db, logger):
    """Monitor the bot thread and restart it if needed"""
    current_thread = initial_thread
    while True:
        if not current_thread.is_alive():
            logger.warning("Bot Discord não está rodando! Reiniciando...")
            new_thread = threading.Thread(target=run_discord_bot, args=(db, logger))
            new_thread.daemon = True
            new_thread.start()
            current_thread = new_thread
            logger.info("Bot Discord reiniciado")
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    # Existing setup code...
    logger = Logger("Main")
    logger.info("Iniciando aplicação Arena Ranking")
    
    db = connect_db()
    
    if db is not None:
        # Existing initialization...
        create_collections(db)
        scheduler = TaskScheduler()
        scheduler.add_task(
            name="process_mmr", 
            interval_minutes=MMR_UPDATE_INTERVAL if 'MMR_UPDATE_INTERVAL' in globals() else 2, 
            task_function=processar_mmr_todos_jogadores,
            db=db
        )
        scheduler.start()
        
        # Start Discord bot in a thread
        bot_thread = threading.Thread(target=run_discord_bot, args=(db, logger))
        bot_thread.daemon = True
        bot_thread.start()
        
        # Start the keep-alive pinger
        keep_alive_thread = threading.Thread(target=keep_alive, args=(logger,))
        keep_alive_thread.daemon = True
        keep_alive_thread.start()
        
        # Start the bot watchdog
        watchdog_thread = threading.Thread(target=bot_watchdog, args=(bot_thread, db, logger))
        watchdog_thread.daemon = True
        watchdog_thread.start()
        
        # Existing web server startup...
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port)
    else:
        logger.error("Falha ao conectar ao banco de dados. Aplicação não pode iniciar.")
