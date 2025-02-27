import pandas as pd
import ipeadatapy
import time
from sqlalchemy import create_engine, text
import os

# Parâmetros para busca de dados no IPEA Data
parametros = {
    "dados_ipeadata": {
        "rendimento": "PNADC12_RRTH12",
        "forca_trabalho": "PNADC12_FT12",
        "desocupacao": "PNADC12_TDESOC12",
        "caged_novo": "CAGED12_SALDON12",
        "caged_antigo": "CAGED12_SALDO12",
        "bovespa": "ANBIMA12_IBVSP12",
        "ettj": "ANBIMA12_TJTLN1212",
        "exportacoes": "PAN12_XTV12",
        "importacoes": "PAN12_MTV12",
        "m1": "BM12_M1MN12",
        "dolar": "PAN12_ERV12",
        "ibc_br": "SGS12_IBCBR12"
    }
}

# Configuração do PostgreSQL (assumindo que está rodando no Docker)
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5433")
DB_NAME = os.getenv("POSTGRES_DB", "ipeadata")

# Criando a conexão com o PostgreSQL usando SQLAlchemy
engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# Função para criar tabelas específicas para cada indicador
def criar_tabelas():
    with engine.connect() as connection:
        for nome_indicador in parametros["dados_ipeadata"].keys():
            tabela = f"ipea_{nome_indicador}"
            print(f"🔹 Criando/verificando tabela: {tabela}")

            connection.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {tabela} (
                    id SERIAL PRIMARY KEY,
                    data DATE UNIQUE,
                    valor FLOAT
                )
            """))
        connection.commit()

# Função para buscar e inserir os dados no PostgreSQL com pausas
def buscar_e_inserir_dados():
    with engine.connect() as connection:
        for nome_indicador, codigo in parametros["dados_ipeadata"].items():
            tabela = f"ipea_{nome_indicador}"
            print(f"\n📥 Baixando dados para: {nome_indicador} ({codigo})")

            try:
                df = ipeadatapy.timeseries(codigo)

                # Verificar se há dados
                if df.empty:
                    print(f"⚠️ Nenhum dado encontrado para {nome_indicador}.")
                    continue

                # Exibir as colunas disponíveis para diagnóstico
                print(f"📊 Colunas disponíveis para {nome_indicador}: {df.columns.tolist()}")

                # Determinar a coluna de data
                if 'RAW DATE' in df.columns:
                    df['data'] = pd.to_datetime(df['RAW DATE'], utc=True, errors='coerce')
                elif {'DAY', 'MONTH', 'YEAR'}.issubset(df.columns):
                    df['data'] = pd.to_datetime(df[['YEAR', 'MONTH', 'DAY']], utc=True, errors='coerce')
                else:
                    print(f"❌ Estrutura inesperada para {nome_indicador}. Colunas recebidas: {df.columns.tolist()}")
                    continue

                # Determinar a coluna de valor
                valor_coluna = next((col for col in df.columns if 'VALUE' in col), None)

                if valor_coluna:
                    df = df[['data', valor_coluna]].rename(columns={valor_coluna: 'valor'})
                else:
                    print(f"❌ Nenhuma coluna de valor encontrada para {nome_indicador}. Colunas recebidas: {df.columns.tolist()}")
                    continue

                # Remover linhas com valores inválidos (`NaT`, `NaN` ou `None`)
                df.dropna(subset=['data', 'valor'], inplace=True)

                # Remover valores negativos inconsistentes no `ibc_br`
                if nome_indicador == "ibc_br":
                    df = df[df['valor'] >= 0]

                # Inserindo os dados no PostgreSQL
                for _, row in df.iterrows():
                    connection.execute(text(f"""
                        INSERT INTO {tabela} (data, valor)
                        VALUES (:data, :valor)
                        ON CONFLICT (data) DO UPDATE SET valor = EXCLUDED.valor
                    """), {"data": row['data'], "valor": row['valor']})

                connection.commit()
                print(f"✅ Dados inseridos na tabela {tabela} com sucesso!")

            except Exception as e:
                print(f"❌ Erro ao buscar dados de {nome_indicador}: {e}")

            # Adicionando uma pausa de 2 segundos para evitar sobrecarga
            time.sleep(2)

# Executando as funções
if __name__ == "__main__":
    criar_tabelas()
    buscar_e_inserir_dados()
    print("\n🚀 Processo finalizado!")
