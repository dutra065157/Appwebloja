const express = require('express');
const cors = require('cors');
const path = require('path');
const { connectToDb } = require('./database');
const { ObjectId } = require('mongodb'); // Importante para buscar por ID

// Tentar importar e configurar Cloudinary
let cloudinary;
let CLOUDINARY_AVAILABLE = false;
try {
    cloudinary = require('cloudinary').v2;
    cloudinary.config({
        cloud_name: 'dxgd62afy',
        api_key: '965736457473817',
        api_secret: 'm0JaTO4RGehmeZexoqjW6cGkLfs',
        secure: true
    });
    CLOUDINARY_AVAILABLE = true;
} catch (e) {
    console.warn("⚠️ Cloudinary não instalado. Para instalar, rode: npm install cloudinary");
}

// Configuração
const PORT = process.env.PORT || 8000;
const app = express();

// Configuração do WhatsApp
const WHATSAPP_CONFIG = {
    api_url: 'https://api.whatsapp.com/send',
    phone_number: '5519987790800',
    default_message: 'Olá! Gostaria de mais informações sobre os produtos.'
};

// Middlewares
app.use(cors()); // Habilita CORS para todas as rotas
app.use(express.json({ limit: '10mb' })); // Permite receber JSON no corpo das requisições
app.use(express.static(__dirname)); // Serve arquivos estáticos (html, css, js) da pasta raiz

// --- ROTAS DA API ---

// Rota de Health Check
app.get('/api/health', async (req, res) => {
    try {
        const db = await connectToDb();
        const products_count = await db.collection('produtos').countDocuments();
        res.status(200).json({
            status: 'OK',
            message: 'Graça Presentes Backend rodando!',
            features: {
                whatsapp_integration: true,
                cloudinary_integration: CLOUDINARY_AVAILABLE,
                database: 'MongoDB',
                products_count: products_count
            }
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Rota para buscar todos os produtos
app.get('/api/produtos', async (req, res) => {
    try {
        const db = await connectToDb();
        // No MongoDB, o ID é `_id`. Vamos renomeá-lo para `id` para manter a compatibilidade com o frontend.
        const produtos = await db.collection('produtos').find().sort({ createdAt: -1 }).toArray();
        res.status(200).json(produtos.map(p => ({ ...p, id: p._id })));
    } catch (error) {
        console.error(`❌ Erro ao buscar produtos: ${error.message}`);
        res.status(500).json({ error: `Erro ao buscar produtos: ${error.message}` });
    }
});

// Rota para cadastrar um novo produto
app.post('/api/produtos', async (req, res) => {
    try {
        const db = await connectToDb();
        const p = req.body;
        const newProduct = {
            nome: p.nome,
            preco: p.preco,
            preco_original: p.preco_original,
            categoria: p.categoria,
            descricao: p.descricao,
            imagem_url: p.imagem_url,
            icone: p.icone || 'box',
            cor: p.cor || 'gray',
            cor_gradiente: p.cor_gradiente || 'from-gray-400 to-gray-600',
            desconto: p.desconto || 0,
            novo: p.novo || false,
            mais_vendido: p.mais_vendido || false,
            createdAt: new Date() // Adicionamos a data de criação
        };
        const result = await db.collection('produtos').insertOne(newProduct);

        res.status(200).json({
            success: true,
            produto_id: result.insertedId,
            message: 'Produto cadastrado com sucesso'
        });
    } catch (error) {
        console.error(`❌ Erro ao cadastrar produto: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

// Rota para buscar todos os pedidos
app.get('/api/pedidos', async (req, res) => {
    try {
        const db = await connectToDb();
        const pedidos = await db.collection('pedidos').find().sort({ dataCriacao: -1 }).toArray();
        res.status(200).json(pedidos.map(p => ({ ...p, id: p._id })));
    } catch (error) {
        console.error(`❌ Erro ao buscar pedidos: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

// Rota para criar um novo pedido
app.post('/api/pedidos', async (req, res) => {
    try {
        const db = await connectToDb();
        const { cliente, itens, total } = req.body;

        if (!cliente || !cliente.nome) {
            return res.status(400).json({ success: false, error: "Dados do cliente são obrigatórios" });
        }

        // No MongoDB, podemos "embutir" os itens dentro do próprio pedido.
        const newOrder = {
            cliente_nome: cliente.nome,
            cliente_email: cliente.email,
            cliente_telefone: cliente.telefone,
            endereco_entrega: cliente.endereco,
            observacoes: cliente.observacoes,
            total: total,
            itens: itens, // Array de itens diretamente no documento
            status: 'recebido',
            dataCriacao: new Date()
        };

        const result = await db.collection('pedidos').insertOne(newOrder);
        const mensagem = `📦 Novo pedido #${result.insertedId.toString().slice(-6)} recebido na Graça Presentes!`;
        const whatsapp_link = `https://api.whatsapp.com/send?phone=${WHATSAPP_CONFIG.phone_number}&text=${encodeURIComponent(mensagem)}`;

        res.status(200).json({
            success: true,
            message: 'Pedido criado com sucesso!',
            pedido_id: result.insertedId,
            whatsapp_link: whatsapp_link
        });

    } catch (error) {
        console.error(`❌ Erro ao processar pedido: ${error.message}`);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Rota para upload de imagem
app.post('/api/upload-imagem', async (req, res) => {
    if (!CLOUDINARY_AVAILABLE) {
        return res.status(500).json({ error: 'Cloudinary não disponível' });
    }

    try {
        const db = await connectToDb();
        const { imagem_base64, produto_id } = req.body;

        const result = await cloudinary.uploader.upload(
            imagem_base64, // O SDK do Node.js aceita o Data URI completo
            {
                folder: "graca-presentes",
                public_id: `produto_${produto_id}`,
                overwrite: true
            }
        );

        await db.collection('produtos').updateOne(
            { _id: new ObjectId(produto_id) }, // Filtro para encontrar o produto pelo seu _id
            { $set: { // Operador para atualizar os campos
                imagem_url: result.secure_url, 
                imagem_public_id: result.public_id 
            }}
        );

        res.status(200).json({
            success: true,
            imagem_url: result.secure_url,
            public_id: result.public_id,
            message: 'Imagem enviada com sucesso!'
        });

    } catch (error) {
        console.error(`❌ Erro no upload: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

// Rota fallback para servir o index.html em rotas não encontradas (para SPAs)
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// --- INICIALIZAÇÃO DO SERVIDOR ---

async function startServer() {
    await connectToDb(); // Garante que a conexão com o DB está pronta
    app.listen(PORT, () => {
        console.log("🚀 GRAÇA PRESENTES - Servidor Node.js Iniciado!");
        console.log(`📍 URL: http://localhost:${PORT}`);
        console.log("💾 Banco de dados: MongoDB");
        console.log("☁️ Cloudinary:", CLOUDINARY_AVAILABLE ? "✅ Disponível" : "❌ Não instalado");
        console.log("⏹️ Para parar: Ctrl+C");
        console.log("=" * 60);
    });
}

startServer().catch(e => console.error("❌ Falha ao iniciar o servidor:", e));