const { MongoClient, ServerApiVersion } = require('mongodb');
require('dotenv').config(); // Carrega as variáveis do arquivo .env

const uri = process.env.MONGODB_URI;
if (!uri) {
    throw new Error('A variável de ambiente MONGODB_URI não está definida. Crie um arquivo .env.');
}

const client = new MongoClient(uri, {
    serverApi: {
        version: ServerApiVersion.v1,
        strict: true,
        deprecationErrors: true,
    }
});

let db;

async function connect() {
    if (db) return;
    try {
        await client.connect();
        // O nome do banco de dados é definido na sua connection string, 
        // ou você pode especificá-lo aqui. Ex: client.db("graca_presentes")
        db = client.db(); 
        console.log("✅ Conectado ao MongoDB com sucesso!");
    } catch (error) {
        console.error("❌ Erro ao conectar ao MongoDB", error);
        process.exit(1); // Encerra a aplicação se não conseguir conectar ao DB
    }
}

connect(); // Conecta assim que o módulo é carregado

module.exports = () => db; // Exporta uma função que retorna a instância do DB já conectado