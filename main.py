import threading
import os
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

if __name__ == "__main__":
    # Configurar logger
    logger = Logger("Main")
    logger.info("Iniciando aplicação Arena Ranking")
    
    # Conectar ao MongoDB
    logger.info("Tentando conectar ao MongoDB Atlas...")
    db = connect_db()
    
    if db is not None:
        logger.info("Conectado ao MongoDB Atlas!")
        create_collections(db)
        
        # Inicializar o agendador
        scheduler = TaskScheduler()
        
        # Adicionar tarefa de processamento de MMR
        scheduler.add_task(
            name="process_mmr", 
            interval_minutes=MMR_UPDATE_INTERVAL if 'MMR_UPDATE_INTERVAL' in globals() else 2, 
            task_function=processar_mmr_todos_jogadores,
            db=db
        )
        
        # Iniciar o agendador em uma thread separada
        scheduler.start()
        logger.info("Agendamento de tarefa MMR configurado.")
        
        # Start Discord bot in a separate thread
        bot_thread = threading.Thread(target=run_discord_bot, args=(db, logger))
        bot_thread.daemon = True
        bot_thread.start()
        
        # Get port from environment (for render.com) or use default
        port = int(os.environ.get('PORT', 5000))
        
        # Start the web server
        logger.info(f"Iniciando servidor web na porta {port}...")
        app.run(host='0.0.0.0', port=port)
    else:
        logger.error("Falha ao conectar ao banco de dados. Aplicação não pode iniciar.")
