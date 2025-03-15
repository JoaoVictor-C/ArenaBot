from typing import Optional
import pymongo
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from database.player_repository import Player
from config.config import MONGODB_URI
from config.config import RIOT_API_KEY as riot_key

def connect_db() -> Optional[Database]:
    """
    Estabelece conexão com o MongoDB Atlas.
    
    Returns:
        Database: Objeto de conexão ao banco de dados MongoDB, ou None em caso de falha.
    """
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        # Verifica se a conexão foi bem-sucedida
        client.admin.command('ping')
        db = client['arena_ranking']
        return db
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        print(f"Erro ao conectar ao MongoDB: {e}")
        return None
    except Exception as e:
        print(f"Erro inesperado ao conectar ao MongoDB: {e}")
        return None

def create_collections(db: Database) -> None:
    """
    Cria as coleções necessárias no banco de dados se não existirem.
    
    Args:
        db: Conexão com o banco de dados MongoDB.
    """
    if db is None:
        print("Erro: Não é possível criar coleções. Conexão de banco de dados é None.")
        return
        
    try:
        # Cria coleção de jogadores se não existir
        if 'players' not in db.list_collection_names():
            db.create_collection('players')
            print("Coleção 'players' criada com sucesso.")
            
            # Criar índices para melhorar performance
            db.players.create_index([("puuid", pymongo.ASCENDING)], unique=True)
            db.players.create_index([("riot_id", pymongo.ASCENDING)])
            print("Índices da coleção 'players' criados com sucesso.")
            
        # Cria coleção de partidas se não existir
        if 'matches' not in db.list_collection_names():
            db.create_collection('matches')
            print("Coleção 'matches' criada com sucesso.")
            
            # Criar índice para match_id
            db.matches.create_index([("match_id", pymongo.ASCENDING)], unique=True)
            print("Índices da coleção 'matches' criados com sucesso.")
    except Exception as e:
        print(f"Erro ao criar coleções: {e}")

def get_all_jogadores(db) -> list[Player]:
    """Retorna os primeiros 50 jogadores do banco de dados."""
    if db is None:
        print("Conexão com o banco de dados não estabelecida. Não é possível recuperar jogadores.")
        return []

    players_collection = db.get_collection('players')
    jogadores_docs = list(players_collection.find().sort("mmr_atual").limit(50))
    
    if jogadores_docs:
        print(f"Recuperados os primeiros {len(jogadores_docs)} jogadores do banco de dados.")
        return [Player.from_document(doc) for doc in jogadores_docs]
    else:
        print("Nenhum jogador encontrado no banco de dados.")
        return []

def add_jogador(db, puuid: str, riot_id: str, nome: str, from_bot: bool, mmr: int = 1000) -> bool:
    """Adds a player to the database if they do not already exist.
    If player exists but auto_check is False, it changes it to True."""
    if db is None:
        print("Database connection is not established. Cannot add player.")
        return False

    players_collection = db.get_collection('players')
    
    existing_player_doc = players_collection.find_one({"puuid": puuid})
    if existing_player_doc:
        print(f"Player with puuid '{puuid}' already exists in the database.")
        
        # Se o auto_check for False, atualize para True
        if not existing_player_doc.get('auto_check', False):
            print(f"Updating auto_check for player with puuid '{puuid}' to True.")
            players_collection.update_one(
                {"puuid": puuid},
                {"$set": {"auto_check": True, "mmr_atual": 1000}}
            )
            return True
        return False

    try:
        new_player = Player(
            puuid=puuid,
            riot_id=riot_id,
            nome=nome,
            mmr_atual=mmr,
            auto_check=from_bot
        )
        players_collection.insert_one(new_player.to_document())
        print(f"Player '{riot_id}' added to the database.")
        return True
    except Exception as e:
        print(f"Error adding player '{riot_id}' to database: {e}")
        return False

def get_jogador_by_riot_id(db, riot_id) -> Optional[Player]:
    """Retrieves a player from the database by their riot_id. Example of riot_id: "Riot ID#1"."""
    
    if db is None:
        print("Database connection is not established. Cannot retrieve player.")
        return None

    players_collection = db.get_collection('players')
    player_doc = players_collection.find_one({"riot_id": riot_id})
    
    if player_doc:
        print(f"Player with riot_id '{riot_id}' found in database.")
        players_collection.update_one(
            {"riot_id": riot_id},
            {"$set": {"auto_check": True, "mmr_atual": 1000, "losses": 0, "wins": 0}}
        )
        return Player.from_document(player_doc)
    else:
        print(f"Player '{riot_id}' not found in database.")
        return None

def get_jogador_by_puuid(db, puuid: str) -> Optional[Player]:
    """Retrieves a player from the database by their puuid."""
    if db is None:
        print("Database connection is not established. Cannot retrieve player.")
        return None

    players_collection = db.get_collection('players')
    player_doc = players_collection.find_one({"puuid": puuid})
    
    if player_doc:
        print(f"Player with puuid '{puuid}' found in database.")
        players_collection.update_one(
            {"puuid": puuid},
            {"$set": {"auto_check": True, "mmr_atual": 1000, "losses": 0, "wins": 0}}
        )
        return Player.from_document(player_doc)
    else:
        print(f"Player with puuid '{puuid}' not found in database.")
        return None

def update_mmr(db, puuid: str, new_mmr: int) -> bool:
    """Updates the MMR of a player in the database."""
    if db is None:
        print("Database connection is not established. Cannot update MMR.")
        return False

    players_collection = db.get_collection('players')
    result = players_collection.update_one(
        {"puuid": puuid},
        {"$set": {"mmr_atual": new_mmr}}
    )
    
    if result.modified_count > 0:
        print(f"MMR updated for player with puuid '{puuid}'.")
        return True
    else:
        print(f"Player with puuid '{puuid}' not found in database.")
        return False
    
def update_player_name(db, puuid: str, new_name: str) -> bool:
    """Updates the display name of a player in the database."""
    if db is None:
        print("Database connection is not established. Cannot update player name.")
        return False

    players_collection = db.get_collection('players')
    result = players_collection.update_one(
        {"puuid": puuid},
        {"$set": {"nome": new_name}}
    )
    
    if result.modified_count > 0:
        print(f"Display name updated for player with puuid '{puuid}'.")
        return True
    else:
        print(f"Player with puuid '{puuid}' not found in database.")
        return False
    
def get_bot_config(db) -> dict:
    """Retrieves the bot configuration from the database."""
    if db is None:
        print("Database connection is not established. Cannot retrieve bot config.")
        return {}

    settings_collection = db.get_collection('bot_settings')
    config_doc = settings_collection.find_one({"config_id": 1})
    
    if config_doc:
        print("Bot config retrieved from database.")
        return config_doc
    else:
        print("Bot config not found in database.")
        return {}
    
def update_bot_config(db, new_config: dict) -> bool: 
    """Updates the bot configuration in the database."""
    if db is None:
        print("Database connection is not established. Cannot update bot config.")
        return False

    settings_collection = db.get_collection('bot_settings')
    result = settings_collection.update_one(
        {"config_id": 1},
        {"$set": new_config}
    )
    
    if result.modified_count > 0:
        print("Bot config updated in database.")
        return True
    else:
        print("Bot config not found in database.")
        return False