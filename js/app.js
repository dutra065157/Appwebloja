// Função para inicializar o menu mobile
function initializeMobileMenu() {
    const menuButton = document.getElementById('mobile-menu-button');
    const mobileMenu = document.getElementById('mobile-menu');

    if (menuButton && mobileMenu) {
        menuButton.addEventListener('click', (event) => {
            event.stopPropagation(); // Impede que o clique se propague para o document
            mobileMenu.classList.toggle('hidden');
            const isHidden = mobileMenu.classList.contains('hidden');
            menuButton.querySelector('i').setAttribute('data-feather', isHidden ? 'menu' : 'x');
            if (typeof feather !== 'undefined') {
                feather.replace();
            }
        });

        // Fecha o menu ao clicar fora dele
        document.addEventListener('click', (event) => {
            if (!mobileMenu.contains(event.target) && !menuButton.contains(event.target)) {
                if (!mobileMenu.classList.contains('hidden')) {
                    mobileMenu.classList.add('hidden');
                    menuButton.querySelector('i').setAttribute('data-feather', 'menu');
                    if (typeof feather !== 'undefined') feather.replace();
                }
            }
        });
    }
}

// Inicializa os componentes quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', () => {
    initializeMobileMenu();
    // Outras inicializações podem vir aqui
});