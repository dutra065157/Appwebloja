const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
require('dotenv').config(); // Garante que as variáveis de ambiente sejam carregadas
const getDb = require('./database'); // Alterado para o novo padrão de conexão
const { ObjectId } = require('mongodb');

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
app.use(express.json({ limit: '10mb' })); // Aumenta o limite para receber imagens em base64

// 📁 Servir a pasta de uploads como estática
const uploadsDir = path.join(__dirname, 'uploads');
if (!fs.existsSync(uploadsDir)) {
    fs.mkdirSync(uploadsDir); // Cria a pasta 'uploads' se ela não existir
}
app.use('/uploads', express.static(uploadsDir));
app.use(express.static(__dirname)); // Serve arquivos estáticos (html, css, js) da pasta raiz

// Middleware de tratamento de erros
const errorHandler = (err, req, res, next) => {
    console.error(`❌ Erro Inesperado: ${err.message}`);
    console.error(err.stack);
    res.status(500).json({ error: 'Ocorreu um erro inesperado no servidor.' });
};

// --- ROTAS DA API ---

// Rota de Health Check
app.get('/api/health', async (req, res) => {
    try {
        const db = getDb();
        const products_count = await db.collection('produtos').countDocuments();
        res.status(200).json({
            status: 'OK',
            message: 'Graça Presentes Backend rodando!',
            features: {
                whatsapp_integration: true,                
                database: 'MongoDB',
                products_count: products_count
            }
        });
    } catch (error) {
        // Passa o erro para o próximo middleware (o errorHandler)
        next(error);
    }
});

// Rota para buscar todos os produtos
app.get('/api/produtos', async (req, res) => {
    try {
        const db = getDb();
        // O frontend espera um campo 'id', então vamos mapear o '_id' do MongoDB para 'id'.
        const produtos = await db.collection('produtos').find().sort({ createdAt: -1 }).toArray();
        res.status(200).json(produtos.map(p => ({ ...p, id: p._id }))); // Mantém compatibilidade
    } catch (error) {
        next(error);
    }
});

// Rota para cadastrar um novo produto
app.post('/api/produtos', async (req, res) => {
    try {
        const db = getDb();
        const p = req.body;

        // Lógica para definir ícone e gradiente com base na categoria
        const categoryStyles = getCategoryStyles(p.categoria);

        const newProduct = {
            nome: p.nome,
            preco: p.preco,
            preco_original: p.preco_original,
            categoria: p.categoria,
            descricao: p.descricao,
            imagem_url: null, // A imagem será adicionada depois
            icone: categoryStyles.icone,
            cor: categoryStyles.cor,
            cor_gradiente: categoryStyles.cor_gradiente,
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
        next(error);
    }
});

// Rota para buscar todos os pedidos
app.get('/api/pedidos', async (req, res) => {
    try {
        const db = getDb();
        const pedidos = await db.collection('pedidos').find().sort({ dataCriacao: -1 }).toArray();
        res.status(200).json(pedidos.map(p => ({ ...p, id: p._id })));
    } catch (error) {
        next(error);
    }
});

// Rota para criar um novo pedido
app.post('/api/pedidos', async (req, res) => {
    try {
        const db = getDb();
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
        next(error);
    }
});

// Rota para upload de imagem
// Esta rota agora salva o arquivo localmente e atualiza o produto no DB.
app.post('/api/upload-imagem', async (req, res, next) => {
    try {
        const { imagem_base64, produto_id } = req.body;

        if (!imagem_base64 || !produto_id) {
            return res.status(400).json({ error: 'Imagem e ID do produto são obrigatórios.' });
        }

        // Extrai o tipo de imagem (ex: 'jpeg') e os dados da string base64
        const matches = imagem_base64.match(/^data:image\/([A-Za-z-+\/]+);base64,(.+)$/);
        if (!matches || matches.length !== 3) {
            return res.status(400).json({ error: 'Formato de imagem base64 inválido.' });
        }

        const imageType = matches[1];
        const imageBuffer = Buffer.from(matches[2], 'base64');
        const imageName = `produto_${produto_id}.${imageType}`;
        const imagePath = path.join(uploadsDir, imageName);

        // Salva o arquivo no disco
        fs.writeFileSync(imagePath, imageBuffer);

        // Cria a URL pública para a imagem (ex: /uploads/produto_65a5b...f.jpeg)
        const imageUrl = `/uploads/${imageName}`; // Ex: /uploads/produto_65a5b...f.jpeg

        // Atualiza o produto no banco de dados com a URL local
        const db = getDb();
        await db.collection('produtos').updateOne(
            { _id: new ObjectId(produto_id) },
            { $set: { imagem_url: imageUrl } }
        );

        res.status(200).json({ success: true, imagem_url: imageUrl, message: 'Imagem salva com sucesso!' });

    } catch (error) {
        next(error);
    }
});

// Rota fallback para servir o index.html em rotas não encontradas (para SPAs)
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Adiciona o middleware de tratamento de erros no final, depois de todas as rotas
app.use(errorHandler);

// --- INICIALIZAÇÃO DO SERVIDOR ---

app.listen(PORT, () => {
    console.log("🚀 GRAÇA PRESENTES - Servidor Node.js Iniciado!");
    console.log(`📍 URL: http://localhost:${PORT}`);
    console.log("💾 Banco de dados: MongoDB");
    console.log("🖼️  Upload de Imagens: Local (pasta /uploads)");
    console.log("⏹️ Para parar: Ctrl+C");
    console.log("=" * 60);
});

// Função auxiliar para estilos de categoria
function getCategoryStyles(categoria) {
    const styles = {
        'Flores': { cor: 'pink', icone: 'sun', cor_gradiente: 'from-pink-200 to-rose-300' },
        'Doces': { cor: 'yellow', icone: 'box', cor_gradiente: 'from-yellow-200 to-amber-300' },
        'Pelúcias': { cor: 'purple', icone: 'heart', cor_gradiente: 'from-purple-200 to-pink-300' },
        'Cosméticos': { cor: 'rose', icone: 'star', cor_gradiente: 'from-rose-200 to-pink-300' },
        'Kits': { cor: 'amber', icone: 'package', cor_gradiente: 'from-amber-200 to-orange-300' },
        'Decoração': { cor: 'blue', icone: 'home', cor_gradiente: 'from-blue-200 to-cyan-300' },
        'Joias': { cor: 'green', icone: 'award', cor_gradiente: 'from-green-200 to-emerald-300' },
        'Românticos': { cor: 'rose', icone: 'heart', cor_gradiente: 'from-rose-200 to-red-300' }
    };
    return styles[categoria] || { cor: 'gray', icone: 'gift', cor_gradiente: 'from-gray-400 to-gray-600' };
}