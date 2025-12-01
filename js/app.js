// API functions
async function carregarProdutos() {
    try {
        const response = await fetch('/api/produtos');
        const produtos = await response.json();
        console.log('Produtos carregados:', produtos);
        return produtos;
    } catch (error) {
        console.error('Erro ao carregar produtos:', error);
        return [];
    }
}

// Inicialização
document.addEventListener('DOMContentLoaded', function() {
    console.log('Graça Presentes - App inicializado');
});