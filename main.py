import flet as ft
from datetime import datetime
import asyncio
import os
import traceback
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
import logging
from dotenv import load_dotenv
load_dotenv()

# Configurar logging

DATABASE_URL = os.environ.get('DATABASE_URL')
logging.basicConfig(level=logging.INFO)

# ==============================================================
# CONFIGURAÇÃO DO BANCO DE DADOS (POSTGRESQL)
# ==============================================================

def get_connection():
    """Estabelece conexão com o banco PostgreSQL"""
    try:
        # Render usa essa variável de ambiente por padrão
        DATABASE_URL = os.environ['DATABASE_URL']
        
        # Ajuste necessário para conexão SSL
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
            
        conn = psycopg2.connect(
            DATABASE_URL,
            sslmode='require',
            cursor_factory=RealDictCursor
        )
        logging.info("Conexão com PostgreSQL estabelecida com sucesso!")
        return conn
    except Exception as e:
        logging.error(f"Erro ao conectar ao PostgreSQL: {str(e)}")
        raise

def criar_banco():
    """Cria as tabelas do banco de dados se não existirem"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Tabela de produtos
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            codigo TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            preco NUMERIC NOT NULL,
            quantidade INTEGER NOT NULL,
            categoria TEXT NOT NULL,
            descricao TEXT,
            data_cadastro TEXT NOT NULL,
            image_path TEXT
        )
        ''')

        # Tabela de vendas
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id SERIAL PRIMARY KEY,
            data_venda TEXT NOT NULL,
            total NUMERIC NOT NULL,
            forma_pagamento TEXT NOT NULL,
            valor_recebido NUMERIC,
            troco NUMERIC
        )
        ''')

        # Tabela de itens vendidos
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS itens_vendidos (
            id SERIAL PRIMARY KEY,
            venda_id INTEGER NOT NULL REFERENCES vendas(id),
            produto_codigo TEXT NOT NULL REFERENCES produtos(codigo),
            nome TEXT NOT NULL,
            preco_unitario NUMERIC NOT NULL,
            quantidade INTEGER NOT NULL,
            subtotal NUMERIC NOT NULL
        )
        ''')

        conn.commit()
        logging.info("Tabelas criadas/verificadas com sucesso!")
    except Exception as e:
        logging.error(f"Erro ao criar tabelas: {str(e)}")
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()

def salvar_produto_db(produto):
    """Salva ou atualiza um produto no banco de dados"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO produtos
            (codigo, nome, preco, quantidade, categoria, descricao, data_cadastro, image_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (codigo) DO UPDATE SET
                nome = EXCLUDED.nome,
                preco = EXCLUDED.preco,
                quantidade = EXCLUDED.quantidade,
                categoria = EXCLUDED.categoria,
                descricao = EXCLUDED.descricao,
                data_cadastro = EXCLUDED.data_cadastro,
                image_path = EXCLUDED.image_path
        ''', (
            produto['codigo'],
            produto['nome'],
            produto['preco'],
            produto['quantidade'],
            produto['categoria'],
            produto['descricao'],
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            produto.get('image_path', '')
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao salvar produto: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

def buscar_produtos_db(filtro=None):
    """Busca produtos no banco de dados com filtro opcional e conversão de tipos segura"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if filtro:
            cursor.execute('''
                SELECT 
                    codigo, 
                    nome, 
                    preco::FLOAT,  -- Conversão explícita para float
                    quantidade::INTEGER,  -- Conversão explícita para inteiro
                    categoria,
                    descricao,
                    image_path
                FROM produtos
                WHERE codigo ILIKE %s OR nome ILIKE %s
                ORDER BY nome
            ''', (f'%{filtro}%', f'%{filtro}%'))
        else:
            cursor.execute('''
                SELECT 
                    codigo, 
                    nome, 
                    preco::FLOAT, 
                    quantidade::INTEGER,
                    categoria,
                    descricao,
                    image_path
                FROM produtos 
                ORDER BY nome
            ''')
        
        # Converter para lista de dicionários com tipos garantidos
        colunas = [desc[0] for desc in cursor.description]
        produtos = []
        for row in cursor.fetchall():
            produto = dict(zip(colunas, row))
            # Garantir conversão numérica mesmo se o cast do PostgreSQL falhar
            produto['preco'] = float(produto['preco'])
            produto['quantidade'] = int(produto['quantidade'])
            produtos.append(produto)
            
        return produtos
    finally:
        cursor.close()
        conn.close()



def buscar_produto_db(codigo):
    """Busca um único produto por código com conversão segura"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT 
                codigo, 
                nome, 
                preco::FLOAT,
                quantidade::INTEGER,
                categoria,
                descricao,
                image_path
            FROM produtos 
            WHERE codigo = %s
        ''', (codigo,))
        
        colunas = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        
        if not row:
            return None
            
        produto = dict(zip(colunas, row))
        # Conversão redundante para garantir tipos
        produto['preco'] = float(produto['preco'])
        produto['quantidade'] = int(produto['quantidade'])
        
        return produto
    finally:
        cursor.close()
        conn.close()


def excluir_produto_db(codigo):
    """Exclui um produto do banco de dados"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM produtos WHERE codigo = %s', (codigo,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao excluir produto: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

def atualizar_estoque_db(codigo, quantidade):
    """Atualiza o estoque de um produto"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        UPDATE produtos
        SET quantidade = quantidade + %s
        WHERE codigo = %s
        ''', (quantidade, codigo))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao atualizar estoque: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

def registrar_venda_db(venda, itens):
    """Registra uma venda e seus itens no banco de dados"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Insere a venda principal
        cursor.execute('''
        INSERT INTO vendas
        (data_venda, total, forma_pagamento, valor_recebido, troco)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        ''', (
            venda['data_venda'],
            venda['total'],
            venda['forma_pagamento'],
            venda.get('valor_recebido'),
            venda.get('troco')
        ))
        venda_id = cursor.fetchone()['id']

        # Insere os itens vendidos
        for item in itens:
            cursor.execute('''
            INSERT INTO itens_vendidos
            (venda_id, produto_codigo, nome, preco_unitario, quantidade, subtotal)
            VALUES (%s, %s, %s, %s, %s, %s)
            ''', (
                venda_id,
                item['codigo'],
                item['nome'],
                item['preco'],
                item['quantidade'],
                item['subtotal']
            ))

        conn.commit()
        return venda_id
    except Exception as e:
        conn.rollback()
        logging.error(f"Erro ao registrar venda: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

def obter_dados_estoque():
    """Obtém os produtos com maior estoque para relatórios"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT nome, quantidade
            FROM produtos
            ORDER BY quantidade DESC
            LIMIT 5
        ''')
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

def obter_dados_vendas_por_categoria():
    """Obtém as vendas por categoria para relatórios"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT p.categoria, SUM(iv.quantidade) as total_vendido
            FROM itens_vendidos iv
            JOIN produtos p ON iv.produto_codigo = p.codigo
            GROUP BY p.categoria
            ORDER BY total_vendido DESC
            LIMIT 5
        ''')
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

# ==============================================================
# FUNÇÕES AUXILIARES E ESTADO DA APLICAÇÃO
# ==============================================================

class AppState:
    """Classe para gerenciar o estado da aplicação"""
    def __init__(self):
        self.carrinho = []
        self.produto_editando = None
        self.uploaded_image_path = None

def mostrar_mensagem(page, texto, cor=ft.Colors.GREEN):
    """Exibe uma mensagem temporária na interface"""
    page.snack_bar = ft.SnackBar(
        content=ft.Text(texto, color=cor),
        bgcolor=ft.Colors.GREY_900 if page.theme_mode == ft.ThemeMode.DARK else ft.Colors.WHITE,
        behavior=ft.SnackBarBehavior.FLOATING
    )
    page.snack_bar.open = True
    page.update()

def confirmar_acao(page, mensagem, callback):
    """Exibe um diálogo de confirmação para ações críticas"""
    def fechar_dialogo(e):
        dialogo.open = False
        page.update()

    def confirmar(e):
        callback()
        fechar_dialogo(e)

    dialogo = ft.AlertDialog(
        modal=True,
        title=ft.Text("Confirmação"),
        content=ft.Text(mensagem),
        actions=[
            ft.TextButton("Sim", on_click=confirmar),
            ft.TextButton("Não", on_click=fechar_dialogo),
        ],
        actions_alignment=ft.MainAxisAlignment.END
    )

    page.dialog = dialogo
    dialogo.open = True
    page.update()

# ==============================================================
# FUNÇÕES PRINCIPAIS DA APLICAÇÃO
# ==============================================================

def main(page: ft.Page):
    # Configuração inicial da página
    page.title = "Graça Presentes - Sistema de Gerenciamento"
    page.window_width = 1300
    page.window_height = 850
    page.padding = 20
    page.theme_mode = ft.ThemeMode.LIGHT
    page.scroll = ft.ScrollMode.AUTO
    page.fonts = {
        "Poppins": "https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap"
    }
    page.theme = ft.Theme(font_family="Poppins")
    
    # Inicialização do estado da aplicação
    state = AppState()
    
    # ==============================================================
    # COMPONENTES DE INTERFACE
    # ==============================================================
    
    # Elementos de imagem
    image_preview = ft.Image(
        width=300,
        height=200,
        fit=ft.ImageFit.CONTAIN,
        border_radius=ft.border_radius.all(10),
        visible=False
    )

    busca_image_preview = ft.Image(
        width=300,
        height=300,
        fit=ft.ImageFit.CONTAIN,
        border_radius=ft.border_radius.all(10),
        visible=False
    )

    

    # FilePicker para seleção de imagens
    def on_files_selected(e: ft.FilePickerResultEvent):
        if e.files:
            selected_file = e.files[0]
            state.uploaded_image_path = selected_file.path
            image_preview.src = state.uploaded_image_path
            image_preview.visible = True
        else:
            state.uploaded_image_path = None
            image_preview.visible = False
        page.update()

    file_picker = ft.FilePicker(on_result=on_files_selected)
    page.overlay.append(file_picker)

    def pick_files(e):
        file_picker.pick_files(allow_multiple=False)

    # ==============================================================
    # FUNÇÕES DE ATUALIZAÇÃO DE INTERFACE
    # ==============================================================

    def calcular_troco(e):
        """Calcula o troco para pagamentos em dinheiro"""
        try:
            total = sum(item['subtotal'] for item in state.carrinho)
            valor = float(valor_recebido.value)

            if valor >= total:
                troco.value = f"Troco: R$ {valor - total:.2f}"
                troco.visible = True
            else:
                troco.value = "Valor insuficiente!"
                troco.color = ft.Colors.RED
                troco.visible = True
        except ValueError:
            troco.visible = False
        page.update()

    def atualizar_forma_pagamento(e):
        """Mostra/oculta campos de pagamento conforme a forma selecionada"""
        valor_recebido.visible = (forma_pagamento.value == "dinheiro")
        troco.visible = False
        page.update()

    def atualizar_tabela_produtos(filtro=None):
        """Atualiza a tabela de produtos com dados do banco"""
        produtos = buscar_produtos_db(filtro)

        tabela_produtos.rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(p['codigo'], weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(p['nome'])),
                    ft.DataCell(ft.Text(f"R$ {p['preco']:.2f}", color=ft.Colors.GREEN)),
                    ft.DataCell(ft.Text(str(p['quantidade']), 
                               color=ft.Colors.RED if p['quantidade'] < 5 else ft.Colors.BLACK)),
                    ft.DataCell(ft.Text(p['categoria'].capitalize(), 
                               color=ft.Colors.BLUE_700)),
                    ft.DataCell(
                        ft.Row([
                            ft.IconButton(
                                ft.Icons.REMOVE_RED_EYE,
                                icon_color=ft.Colors.BLUE_700,
                                tooltip="Visualizar",
                                on_click=lambda e, cod=p['codigo']: mostrar_modal_produto(cod)
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE,
                                icon_color=ft.Colors.RED_700,
                                tooltip="Excluir",
                                on_click=lambda e, cod=p['codigo']: confirmar_exclusao(cod)
                            ),
                        ], spacing=5)
                    ),
                ],
                on_select_changed=lambda e, cod=p['codigo']: selecionar_produto(cod),
                color=ft.Colors.GREY_100 if idx % 2 == 0 else None
            ) for idx, p in enumerate(produtos)
        ]

        if not produtos:
            tabela_produtos.rows = [
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text("Nenhum produto cadastrado", italic=True)),
                        *[ft.DataCell(ft.Text("")) for _ in range(5)]
                    ]
                )
            ]
        page.update()

    def atualizar_seletor_produtos():
        """Atualiza o dropdown de seleção de produtos"""
        produtos = buscar_produtos_db()
        seletor_produto.options = [
            ft.dropdown.Option(
                p['codigo'],
                f"{p['nome']} (R$ {p['preco']:.2f})"
            ) for p in produtos
        ]
        page.update()

    def limpar_formulario(e=None):
        """Limpa o formulário de cadastro de produtos"""
        state.produto_editando = None
        state.uploaded_image_path = None
        codigo_produto.value = ""
        nome_produto.value = ""
        preco_produto.value = ""
        quantidade_produto.value = ""
        categoria_produto.value = ""
        descricao_produto.value = ""
        image_preview.visible = False
        codigo_produto.focus()
        page.update()

    def cadastrar_produto(e):

        """Salva um novo produto ou atualiza um existente com tratamento de números"""
        campos_obrigatorios = [codigo_produto, nome_produto, preco_produto, quantidade_produto]
        
        # Verificação robusta de campos obrigatórios
        if any(not campo.value or not campo.value.strip() for campo in campos_obrigatorios):
            mostrar_mensagem(page, "Preencha todos os campos obrigatórios!", ft.Colors.RED)
            return

        try:
            # Conversão segura de valores numéricos com tratamento de vírgulas
            preco_valor = float(preco_produto.value.replace(',', '.').strip())
            quantidade_valor = int(quantidade_produto.value.strip())
            
            # Validação de valores positivos
            if preco_valor <= 0:
                mostrar_mensagem(page, "Preço deve ser maior que zero!", ft.Colors.RED)
                return
            if quantidade_valor < 0:
                mostrar_mensagem(page, "Quantidade não pode ser negativa!", ft.Colors.RED)
                return

            produto = {
                'codigo': codigo_produto.value.strip(),
                'nome': nome_produto.value.strip(),
                'preco': preco_valor,  # Usando o valor convertido para float
                'quantidade': quantidade_valor,  # Usando o valor convertido para int
                'categoria': categoria_produto.value.strip() if categoria_produto.value else "outros",
                'descricao': descricao_produto.value.strip() if descricao_produto.value else "",
                'image_path': state.uploaded_image_path
            }

            salvar_produto_db(produto)
            limpar_formulario()
            atualizar_tabela_produtos()
            atualizar_seletor_produtos()
            mostrar_mensagem(page, "✅ Produto salvo com sucesso!")
            
            # Resetar caminho da imagem após cadastro
            state.uploaded_image_path = ""
            page.update()

        except ValueError:
            mostrar_mensagem(page, "Valores inválidos! Preço deve ser número (ex: 9.99) e quantidade inteiro", ft.Colors.RED)
        except Exception as ex:
            mostrar_mensagem(page, f"Erro inesperado: {str(ex)}", ft.Colors.RED)

    def selecionar_produto(codigo):
        """Preenche o formulário com dados de um produto existente"""
        produto = buscar_produto_db(codigo)
        if produto:
            codigo_produto.value = produto['codigo']
            nome_produto.value = produto['nome']
            preco_produto.value = str(produto['preco'])
            quantidade_produto.value = str(produto['quantidade'])
            categoria_produto.value = produto['categoria']
            descricao_produto.value = produto['descricao'] or ""

            if produto['image_path']:
                state.uploaded_image_path = produto['image_path']
                image_preview.src = state.uploaded_image_path
                image_preview.visible = True
            else:
                state.uploaded_image_path = None
                image_preview.visible = False

            page.update()

    # ==============================================================
    # MODAL DE DETALHES DO PRODUTO
    # ==============================================================

    modal_codigo = ft.Text()
    modal_nome = ft.Text()
    modal_preco = ft.Text()
    modal_estoque = ft.Text()
    modal_categoria = ft.Text()
    modal_descricao = ft.Text()
    modal_image = ft.Image(
        width=200,
        height=150,
        fit=ft.ImageFit.CONTAIN,
        border_radius=ft.border_radius.all(5),
        visible=False
    )

    def mostrar_modal_produto(codigo):
        """Exibe modal com detalhes do produto"""
        produto = buscar_produto_db(codigo)
        if produto:
            modal_codigo.value = produto['codigo']
            modal_nome.value = produto['nome']
            modal_preco.value = f"R$ {produto['preco']:.2f}"
            modal_estoque.value = str(produto['quantidade'])
            modal_categoria.value = produto['categoria'].capitalize()
            modal_descricao.value = produto['descricao'] or "Nenhuma descrição"

            if produto['image_path']:
                modal_image.src = produto['image_path']
                modal_image.visible = True
            else:
                modal_image.visible = False

            page.dialog = modal_produto
            modal_produto.open = True
            page.update()

    def fechar_modal():
        modal_produto.open = False
        page.update()

    def editar_produto_modal():
        """Preenche formulário com produto do modal"""
        codigo = modal_codigo.value
        selecionar_produto(codigo)
        fechar_modal()
        codigo_produto.focus()

    def confirmar_exclusao(codigo):
        """Confirma exclusão de produto"""
        def excluir():
            excluir_produto_db(codigo)
            mostrar_mensagem(page, "🗑️ Produto excluído com sucesso!")
            atualizar_tabela_produtos()
            atualizar_seletor_produtos()

        confirmar_acao(page, "Tem certeza que deseja excluir este produto?", excluir)

    # ==============================================================
    # FUNÇÕES DE BUSCA
    # ==============================================================

    def buscar_produto(e=None):
        """Realiza busca de produtos no banco de dados"""
        filtro = campo_busca.value.strip()
        produtos = buscar_produtos_db(filtro if filtro else None)

        busca_image_preview.visible = False

        resultados_busca.controls = [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.INVENTORY_2, color=ft.Colors.BLUE_700),
                title=ft.Text(p['nome'], weight=ft.FontWeight.BOLD),
                subtitle=ft.Text(f"Código: {p['codigo']} | Preço: R$ {p['preco']:.2f} | Estoque: {p['quantidade']}"),
                on_click=lambda e, p=p: selecionar_produto_busca(p),
            ) for p in produtos
        ]

        if not produtos:
            resultados_busca.controls = [
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.SEARCH_OFF),
                    title=ft.Text("Nenhum produto encontrado", italic=True),
                )
            ]

        page.update()

    def selecionar_produto_busca(produto):
        """Mostra imagem do produto na busca"""
        if produto['image_path']:  # Verifica se há caminho de imagem
            busca_image_preview.src = produto['image_path']
            busca_image_preview.visible = True
        else:
            busca_image_preview.visible = False
        page.update()  # Atualiza a página para exibir a imagem

    # ==============================================================
    # FUNÇÕES DO CARRINHO
    # ==============================================================

    def adicionar_ao_carrinho(e):

        """Adiciona produto ao carrinho de compras"""
        codigo = seletor_produto.value
        if not codigo:
            mostrar_mensagem(page, "Selecione um produto", ft.Colors.RED)
            return

        try:
            quantidade = int(quantidade_compra.value)
            if quantidade <= 0:
                mostrar_mensagem(page, "Quantidade deve ser maior que zero", ft.Colors.RED)
                return
        except ValueError:
            mostrar_mensagem(page, "Quantidade inválida", ft.Colors.RED)
            return

        produto = buscar_produto_db(codigo)
        if not produto:
            mostrar_mensagem(page, "Produto não encontrado", ft.Colors.RED)
            return

        # CORREÇÃO: Converter quantidade para int
        estoque_disponivel = int(produto['quantidade'])
        if quantidade > estoque_disponivel:
            mostrar_mensagem(page, f"Quantidade indisponível! Estoque: {estoque_disponivel}", ft.Colors.RED)
            return

        # CORREÇÃO: Converter preço para float
        preco_produto = float(produto['preco'])
        
        item_existente = next(
            (i for i in state.carrinho if i['codigo'] == codigo), None)

        if item_existente:
            # CORREÇÃO: Usar variável convertida
            nova_quantidade = item_existente['quantidade'] + quantidade
            
            # Verificar estoque novamente considerando quantidade existente
            if nova_quantidade > estoque_disponivel:
                mostrar_mensagem(page, 
                    f"Limite excedido! Você já tem {item_existente['quantidade']} no carrinho",
                    ft.Colors.ORANGE)
                return
                
            item_existente['quantidade'] = nova_quantidade
            item_existente['subtotal'] = preco_produto * nova_quantidade
        else:
            # CORREÇÃO: Usar variáveis convertidas
            state.carrinho.append({
                'codigo': codigo,
                'nome': produto['nome'],
                'preco': preco_produto,
                'quantidade': quantidade,
                'subtotal': preco_produto * quantidade
            })

        atualizar_estoque_db(codigo, -quantidade)
        atualizar_carrinho()
        atualizar_tabela_produtos()
        mostrar_mensagem(page, "✅ Produto adicionado ao carrinho!")
        quantidade_compra.value = "1"
        seletor_produto.focus()
        page.update()

    def atualizar_carrinho():
        """Atualiza a exibição do carrinho"""
        itens_carrinho.controls = [
            ft.Card(
                content=ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(f"{item['nome']}", weight=ft.FontWeight.BOLD),
                            ft.Text(f"x{item['quantidade']} | R$ {item['preco']:.2f} un", size=12)
                        ], expand=True),
                        ft.Text(f"R$ {item['subtotal']:.2f}", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
                        ft.IconButton(
                            icon=ft.Icons.DELETE,
                            icon_color=ft.Colors.RED_700,
                            tooltip="Remover",
                            on_click=lambda e, cod=item['codigo']: remover_do_carrinho(cod)
                        )
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=10
                ),
                elevation=2,
                margin=ft.margin.symmetric(vertical=5)
            ) for item in state.carrinho
        ]

        total = sum(item['subtotal'] for item in state.carrinho)
        total_carrinho.value = f"R$ {total:.2f}"
        page.update()

    def remover_do_carrinho(codigo):
        """Remove item do carrinho"""
        item = next((i for i in state.carrinho if i['codigo'] == codigo), None)
        if item:
            atualizar_estoque_db(codigo, item['quantidade'])
            state.carrinho.remove(item)
            atualizar_carrinho()
            atualizar_tabela_produtos()
            mostrar_mensagem(page, "❌ Item removido do carrinho")

    def limpar_carrinho(e):
        """Limpa todos os itens do carrinho"""
        if not state.carrinho:
            return

        def limpar():
            for item in state.carrinho:
                atualizar_estoque_db(item['codigo'], item['quantidade'])
            state.carrinho.clear()
            atualizar_carrinho()
            atualizar_tabela_produtos()
            mostrar_mensagem(page, "🔄 Carrinho limpo")

        confirmar_acao(page, "Tem certeza que deseja limpar o carrinho?", limpar)

    # ==============================================================
    # MODAL DE CHECKOUT
    # ==============================================================

    checkout_itens = ft.Column(scroll=ft.ScrollMode.AUTO)
    checkout_total = ft.Text("R$ 0,00", size=20, weight=ft.FontWeight.BOLD)
    valor_recebido = ft.TextField(
        label="Valor Recebido",
        prefix_text="R$ ",
        visible=False,
        on_change=calcular_troco,
        border_color=ft.Colors.BLUE_700
    )
    troco = ft.Text("Troco: R$ 0,00", visible=False, size=16, weight=ft.FontWeight.BOLD)
    forma_pagamento = ft.Dropdown(
        label="Forma de Pagamento",
        options=[
            ft.dropdown.Option("dinheiro", "Dinheiro"),
            ft.dropdown.Option("cartao", "Cartão"),
            ft.dropdown.Option("pix", "PIX"),
        ],
        value="dinheiro",
        on_change=atualizar_forma_pagamento,
        border_color=ft.Colors.BLUE_700
    )

    def abrir_checkout(e):
        """Abre o modal de finalização de compra"""
        if not state.carrinho:
            mostrar_mensagem(page, "Carrinho vazio", ft.Colors.RED)
            return

        checkout_itens.controls.clear()

        for item in state.carrinho:
            checkout_itens.controls.append(
                ft.Row([
                    ft.Text(f"{item['nome']} x{item['quantidade']}"),
                    ft.Text(f"R$ {item['subtotal']:.2f}", color=ft.Colors.GREEN)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            )

        total = sum(item['subtotal'] for item in state.carrinho)
        checkout_total.value = f"R$ {total:.2f}"

        valor_recebido.value = ""
        forma_pagamento.value = "dinheiro"
        valor_recebido.visible = False
        troco.visible = False

        page.dialog = modal_checkout
        modal_checkout.open = True
        page.update()

    def finalizar_compra(e):
        """Finaliza a venda e registra no banco de dados"""
        try:
            forma_pgto = forma_pagamento.value
            total = sum(item['subtotal'] for item in state.carrinho)

            if forma_pgto == "dinheiro":
                try:
                    valor_pago = float(valor_recebido.value)
                    if valor_pago < total:
                        mostrar_mensagem(page, "Valor insuficiente!", ft.Colors.RED)
                        return
                    troco_valor = valor_pago - total
                except ValueError:
                    mostrar_mensagem(page, "Digite um valor válido!", ft.Colors.RED)
                    return
            else:
                troco_valor = 0.0
                valor_pago = total

            venda = {
                'data_venda': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total': total,
                'forma_pagamento': forma_pgto,
                'valor_recebido': valor_pago if forma_pgto == "dinheiro" else None,
                'troco': troco_valor if forma_pgto == "dinheiro" else None
            }

            venda_id = registrar_venda_db(venda, state.carrinho)
            state.carrinho.clear()
            atualizar_carrinho()
            modal_checkout.open = False
            atualizar_tabela_produtos()

            msg = f"✅ Venda #{venda_id} finalizada com sucesso!"
            if forma_pgto == "dinheiro":
                msg += f" Troco: R$ {troco_valor:.2f}"

            success_vendas_text.value = msg
            page.update()

            # Limpa mensagem após 5 segundos
            async def clear_success():
                await asyncio.sleep(5)
                success_vendas_text.value = ""
                page.update()
            page.run_task(clear_success)

        except Exception as ex:
            mostrar_mensagem(page, f"Erro ao finalizar venda: {str(ex)}", ft.Colors.RED)
            traceback.print_exc()

    def fechar_modal_checkout(e=None):
        """Fecha o modal de checkout"""
        modal_checkout.open = False
        page.update()

    # ==============================================================
    # NAVEGAÇÃO ENTRE PÁGINAS
    # ==============================================================

    def cadastrar_produto_pagina(e):
        """Navega para a página de cadastro de produtos"""
        page.clean()
        page.add(header)
        page.add(ft.Row([form_cadastro, secao_produtos], expand=True))
        page.add(botao_voltar)
        page.update()

    def voltar_pagina_inicial(e):
        """Volta para a página inicial"""
        page.clean()
        page.add(header)
        page.add(ft.Row([
            ft.Column([secao_carrinho, form_busca], expand=2),
            ft.Column([Botao_pagina_cadastro], expand=1)
        ], expand=True))
        page.update()

    def mostrar_relatorios(e):
        """Navega para a página de relatórios"""
        page.clean()
        page.add(header)
        page.add(relatorios_content)
        page.add(botao_voltar)
        page.update()

    # ==============================================================
    # COMPONENTES DE GRÁFICOS
    # ==============================================================

    def criar_grafico_estoque():
        """Cria gráfico de barras para estoque"""
        dados = obter_dados_estoque()
        if not dados:
            return ft.Text("Nenhum dado de estoque disponível", italic=True)

        cores = [
            ft.Colors.AMBER_700,
            ft.Colors.BLUE_700,
            ft.Colors.RED_700,
            ft.Colors.ORANGE_700,
            ft.Colors.GREEN_700
        ]

        max_quantidade = max([p['quantidade'] for p in dados]) * 1.2

        return ft.BarChart(
            bar_groups=[
                ft.BarChartGroup(
                    x=idx,
                    bar_rods=[
                        ft.BarChartRod(
                            from_y=0,
                            to_y=p['quantidade'],
                            width=40,
                            color=cores[idx % len(cores)],
                            tooltip=f"{p['nome']}\nEstoque: {p['quantidade']}",
                            border_radius=5
                        )
                    ]
                ) for idx, p in enumerate(dados)
            ],
            border=ft.border.all(1, ft.Colors.GREY_400),
            left_axis=ft.ChartAxis(
                labels_size=40,
                title=ft.Text("Quantidade em Estoque"),
                title_size=40
            ),
            bottom_axis=ft.ChartAxis(
                labels=[
                    ft.ChartAxisLabel(
                        value=idx,
                        label=ft.Container(
                            ft.Text(p['nome'][:15], weight=ft.FontWeight.BOLD),
                            padding=10
                        )
                    ) for idx, p in enumerate(dados)
                ],
                labels_size=40
            ),
            horizontal_grid_lines=ft.ChartGridLines(
                color=ft.Colors.GREY_300,
                width=1,
                dash_pattern=[3, 3]
            ),
            tooltip_bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.GREY_200),
            max_y=max_quantidade,
            interactive=True,
            expand=True
        )

    def criar_grafico_vendas():
        """Cria gráfico de barras para vendas por categoria"""
        dados = obter_dados_vendas_por_categoria()
        if not dados:
            return ft.Text("Nenhum dado de vendas disponível", italic=True)

        cores = [ft.Colors.PURPLE_700, ft.Colors.INDIGO_700, ft.Colors.BROWN_700,
                 ft.Colors.PINK_700, ft.Colors.CYAN_700]

        max_vendas = max([p['total_vendido'] for p in dados]) * 1.2

        return ft.BarChart(
            bar_groups=[
                ft.BarChartGroup(
                    x=idx,
                    bar_rods=[
                        ft.BarChartRod(
                            from_y=0,
                            to_y=p['total_vendido'],
                            width=40,
                            color=cores[idx % len(cores)],
                            tooltip=f"{p['categoria']}\nVendas: {p['total_vendido']} unidades",
                            border_radius=5
                        )
                    ]
                ) for idx, p in enumerate(dados)
            ],
            border=ft.border.all(1, ft.Colors.GREY_400),
            left_axis=ft.ChartAxis(
                labels_size=40,
                title=ft.Text("Total de Vendas"),
                title_size=40
            ),
            bottom_axis=ft.ChartAxis(
                labels=[
                    ft.ChartAxisLabel(
                        value=idx,
                        label=ft.Container(ft.Text(p['categoria'][:15], weight=ft.FontWeight.BOLD), padding=10)
                    ) for idx, p in enumerate(dados)
                ],
                labels_size=40
            ),
            horizontal_grid_lines=ft.ChartGridLines(
                color=ft.Colors.GREY_300, width=1, dash_pattern=[3, 3]
            ),
            tooltip_bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.GREY_200),
            max_y=max_vendas,
            interactive=True,
            expand=True
        )

    # ==============================================================
    # DEFINIÇÃO DOS COMPONENTES DE INTERFACE
    # ==============================================================

    # Modal de checkout
    modal_checkout = ft.AlertDialog(
        modal=True,
        title=ft.Text(
            "FINALIZAR COMPRA",
            size=24,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
            color=ft.Colors.BLUE_800
        ),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "ITENS DO CARRINHO",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER,
                        color=ft.Colors.BLUE_700
                    ),
                    ft.Divider(height=2, thickness=2, color=ft.Colors.BLUE_100),
                    checkout_itens,
                    ft.Divider(height=2, thickness=2, color=ft.Colors.BLUE_100),
                    ft.Row(
                        [
                            ft.Text(
                                "TOTAL:",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.BLUE_700
                            ),
                            checkout_total
                        ],
                        alignment=ft.MainAxisAlignment.CENTER
                    ),
                    ft.Container(forma_pagamento, padding=ft.padding.symmetric(vertical=10)),
                    ft.Container(valor_recebido, padding=ft.padding.only(bottom=10)),
                    troco
                ],
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            width=600,
            padding=ft.padding.symmetric(horizontal=30, vertical=20),
        ),
        shape=ft.RoundedRectangleBorder(radius=15),
        actions=[
            ft.TextButton(
                "CONFIRMAR",
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.GREEN_700,
                    color=ft.Colors.WHITE,
                    padding=ft.padding.symmetric(horizontal=30, vertical=15),
                    shape=ft.RoundedRectangleBorder(radius=10)
                ),
                on_click=finalizar_compra
            ),
            ft.TextButton(
                "CANCELAR",
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.RED_700,
                    color=ft.Colors.WHITE,
                    padding=ft.padding.symmetric(horizontal=30, vertical=15),
                    shape=ft.RoundedRectangleBorder(radius=10)
                ),
                on_click=fechar_modal_checkout
            )
        ],
        actions_alignment=ft.MainAxisAlignment.SPACE_EVENLY
    )

    page.add(modal_checkout)

    # Modal de produto
    modal_produto = ft.AlertDialog(
        modal=True,
        title=ft.Text("Detalhes do Produto", weight=ft.FontWeight.BOLD),
        content=ft.Column([
            ft.Row([ft.Text("Código:", weight=ft.FontWeight.BOLD), modal_codigo]),
            ft.Row([ft.Text("Nome:", weight=ft.FontWeight.BOLD), modal_nome]),
            ft.Row([ft.Text("Preço:", weight=ft.FontWeight.BOLD), modal_preco]),
            ft.Row([ft.Text("Estoque:", weight=ft.FontWeight.BOLD), modal_estoque]),
            ft.Row([ft.Text("Categoria:", weight=ft.FontWeight.BOLD), modal_categoria]),
            ft.Row([ft.Text("Descrição:", weight=ft.FontWeight.BOLD), modal_descricao]),
            ft.Container(content=modal_image, alignment=ft.alignment.center)
        ], tight=True, spacing=10),
        actions=[
            ft.TextButton("Editar", on_click=editar_produto_modal, 
                         style=ft.ButtonStyle(color=ft.Colors.BLUE_700)),
            ft.TextButton("Excluir", on_click=lambda e, cod=modal_codigo.value: confirmar_exclusao(cod),
                         style=ft.ButtonStyle(color=ft.Colors.RED_700)),
            ft.TextButton("Fechar", on_click=fechar_modal,
                         style=ft.ButtonStyle(color=ft.Colors.GREY_700))
        ],
        actions_alignment=ft.MainAxisAlignment.END
    )

    # Componentes do formulário de cadastro
    codigo_produto = ft.TextField(
        label="Código do Produto", 
        width=300, 
        autofocus=True,
        border_color=ft.Colors.BLUE_700,
        prefix_icon=ft.Icons.LABEL
    )
    nome_produto = ft.TextField(
        label="Nome do Produto", 
        width=300,
        border_color=ft.Colors.BLUE_700,
        prefix_icon=ft.Icons.LABEL
    )
    preco_produto = ft.TextField(
        label="Preço Unitário (R$)", 
        width=300, 
        prefix_text="R$ ",
        border_color=ft.Colors.BLUE_700,
        prefix_icon=ft.Icons.ATTACH_MONEY
    )
    quantidade_produto = ft.TextField(
        label="Quantidade em Estoque", 
        width=300,
        border_color=ft.Colors.BLUE_700,
        prefix_icon=ft.Icons.INVENTORY
    )
    categoria_produto = ft.Dropdown(
        label="Categoria",
        options=[
            ft.dropdown.Option("cosmeticos", "Cosméticos"),
            ft.dropdown.Option("perfumes", "Perfumes"),
            ft.dropdown.Option("cestas", "Cestas"),
            ft.dropdown.Option("higiene", "Higiene"),
            ft.dropdown.Option("outros", "Outros"),
        ],
        width=300,
        border_color=ft.Colors.BLUE_700
    )
    descricao_produto = ft.TextField(
        label="Descrição", 
        multiline=True, 
        min_lines=2, 
        width=300,
        border_color=ft.Colors.BLUE_700,
    )

    # Seção de busca
    campo_busca = ft.TextField(
        label="Buscar Produto",
        width=300,
        suffix_icon=ft.Icons.SEARCH,
        on_submit=buscar_produto,
        border_color=ft.Colors.BLUE_700
    )

    resultados_busca = ft.Column(
        spacing=5, scroll=ft.ScrollMode.AUTO, height=150)

    # Seção de carrinho
    seletor_produto = ft.Dropdown(
        label="Produto", 
        width=300, 
        options=[],
        border_color=ft.Colors.BLUE_700,
        leading_icon=ft.Icons.SHOPPING_BAG
    )
    quantidade_compra = ft.TextField(
        label="Quantidade", 
        value="1", 
        width=100,
        border_color=ft.Colors.BLUE_700
    )
    itens_carrinho = ft.Column(
        spacing=5, scroll=ft.ScrollMode.AUTO, height=150)
    total_carrinho = ft.Text("R$ 0,00", size=18, weight=ft.FontWeight.BOLD)

    # Tabela de produtos
    tabela_produtos = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Código", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Nome", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Preço", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Estoque", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Categoria", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Ações", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
        width=1100,
        heading_row_color=ft.Colors.BLUE_50,
        column_spacing=20
    )

    # Mensagens
    success_vendas_text = ft.Text(size=18, color=ft.Colors.GREEN)

    # ==============================================================
    # LAYOUT PRINCIPAL
    # ==============================================================

    # Cabeçalho
    
    
    header = ft.Container(
        content=ft.Row(
            [
                # Área da Logo + Texto
                ft.Row(
                    [
                        # Logo
                        ft.Container(
                            content=ft.Image(
                                src="imagens/ft.png",
                                height=60,
                                fit=ft.ImageFit.CONTAIN
                            ),
                            padding=ft.padding.only(right=15),
                        ),
                        # Textos
                        ft.Column(
                            [
                                ft.Text(
                                    "GRAÇA PRESENTES",
                                    size=28,
                                    weight=ft.FontWeight.W_800,
                                    color=ft.Colors.WHITE,
                                ),
                                ft.Text(
                                    "Sistema de gerenciamento de produtos",
                                    size=16,
                                    color=ft.Colors.WHITE70,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=3
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER
                ),
                
                # Botões
                ft.Row([
                    ft.IconButton(
                        icon=ft.Icons.INSERT_CHART_ROUNDED,
                        icon_size=30,
                        icon_color=ft.Colors.WHITE,
                        tooltip="Relatórios",
                        on_click=mostrar_relatorios,
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=10),
                            padding=15,
                            overlay_color="#19FFFFFF"  # Branco com 10% de opacidade
                        )
                    ),
                    ft.IconButton(
                        icon=ft.Icons.SHOPPING_CART_CHECKOUT_ROUNDED,
                        icon_size=30,
                        icon_color=ft.Colors.WHITE,
                        tooltip="Finalizar Compra",
                        on_click=abrir_checkout,
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=10),
                            padding=15,
                            overlay_color="#19FFFFFF"  # Branco com 10% de opacidade
                        )
                    )
                ], 
                spacing=15,
                alignment=ft.MainAxisAlignment.END
                )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        ),
        padding=ft.padding.symmetric(horizontal=30, vertical=15),
        border_radius=ft.border_radius.only(bottom_left=25, bottom_right=25),
        margin=ft.margin.only(bottom=25),
        gradient=ft.LinearGradient(
            begin=ft.alignment.top_left,
            end=ft.alignment.bottom_right,
            colors=["#1a237e", "#283593", "#3949ab"]
        ),
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=20,
            color="#800d47a1",  # BLUE_900 com 50% de opacidade
            offset=ft.Offset(0, 6)
        ),
        height=100
    )
    # Formulário de cadastro
    form_cadastro = ft.Container(
        width=400,
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Text("Cadastro de Produtos",
                                    size=20, weight=ft.FontWeight.BOLD),
                    padding=10
                ),
                ft.Divider(),
                codigo_produto,
                nome_produto,
                preco_produto,
                quantidade_produto,
                categoria_produto,
                descricao_produto,
                ft.Container(
                    content=ft.Column([
                        ft.ElevatedButton(
                            "Escolher Imagem",
                            on_click=pick_files,
                            icon=ft.Icons.IMAGE,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.BLUE_700, 
                                color=ft.Colors.WHITE
                            )
                        ),
                        image_preview
                    ], spacing=10),
                    padding=10,
                    alignment=ft.alignment.center
                ),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Limpar",
                            icon=ft.Icons.CLEAR,
                            on_click=limpar_formulario,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.GREY_300, 
                                color=ft.Colors.BLACK
                            )
                        ),
                        ft.ElevatedButton(
                            "Salvar",
                            icon=ft.Icons.SAVE,
                            on_click=cadastrar_produto,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.BLUE_700, 
                                color=ft.Colors.WHITE
                            )
                        )
                    ],
                    spacing=10,
                    alignment=ft.MainAxisAlignment.END
                )
            ],
            scroll=ft.ScrollMode.AUTO
        ),
        padding=10,
        margin=ft.margin.only(right=20),
        border=ft.border.all(1, ft.Colors.GREY_300),
        border_radius=10
    )

    # Busca de produtos
    form_busca = ft.Container(
        content=ft.Column([
            ft.Text("Buscar Produtos", size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            campo_busca,
            ft.ElevatedButton(
                "Buscar",
                icon=ft.Icons.SEARCH,
                on_click=buscar_produto,
                width=300,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_700,
                    color=ft.Colors.WHITE
                )
            ),
            ft.Container(
                content=resultados_busca,
                border=ft.border.all(1, ft.Colors.GREY_300),
                border_radius=5,
                padding=10,
                height=200
            ),
            ft.Container(
                content=busca_image_preview,
                alignment=ft.alignment.center,
                padding=10
            )
        ]),
        padding=10,
        border=ft.border.all(1, ft.Colors.GREY_300),
        border_radius=10
    )

    # Carrinho de compras
    secao_carrinho = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Text("Carrinho de Compras", size=20,
                                    weight=ft.FontWeight.BOLD),
                    padding=10
                ),
                ft.Divider(),
                ft.Row([
                    seletor_produto,
                    quantidade_compra,
                    ft.ElevatedButton(
                        "Adicionar",
                        icon=ft.Icons.ADD,
                        on_click=adicionar_ao_carrinho,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.GREEN_700, 
                            color=ft.Colors.WHITE, 
                            padding=10
                        )
                    )
                ], spacing=10),
                ft.Container(
                    content=itens_carrinho,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=5,
                    padding=10,
                    height=150
                ),
                success_vendas_text,
                ft.Container(
                    content=ft.Row([
                        ft.Text("Total:", size=16, weight=ft.FontWeight.BOLD),
                        total_carrinho
                    ], alignment=ft.MainAxisAlignment.END),
                    padding=10
                ),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Limpar",
                            icon=ft.Icons.DELETE,
                            on_click=limpar_carrinho,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.RED_700, 
                                color=ft.Colors.WHITE
                            )
                        ),
                        ft.ElevatedButton(
                            "Finalizar",
                            icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                            on_click=abrir_checkout,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.ORANGE_700, 
                                color=ft.Colors.WHITE
                            )
                        )
                    ],
                    spacing=10,
                    alignment=ft.MainAxisAlignment.END
                )
            ]
        ),
        padding=10,
        border=ft.border.all(1, ft.Colors.GREY_300),
        border_radius=10
    )

    # Produtos cadastrados
    secao_produtos = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Text("Produtos Cadastrados", size=20,
                                    weight=ft.FontWeight.BOLD),
                    padding=10
                ),
                ft.Divider(),
                ft.Container(
                    content=tabela_produtos,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=5,
                    padding=10,
                    expand=True
                )
            ],
            expand=True
        ),
        padding=10,
        border=ft.border.all(1, ft.Colors.GREY_300),
        border_radius=10,
        expand=True
    )

    # Relatórios
    relatorios_content = ft.Column(
        controls=[
            ft.Container(
                content=ft.Text(
                    "📊 Relatórios de Produtos e Vendas",
                    size=26,
                    weight=ft.FontWeight.BOLD,
                    text_align=ft.TextAlign.CENTER
                ),
                alignment=ft.alignment.center,
                margin=ft.margin.only(top=20)
            ),
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text("Estoque de Produtos", size=20,
                                weight=ft.FontWeight.BOLD),
                        ft.Container(
                            content=criar_grafico_estoque(),
                            height=300,
                            padding=10
                        ),
                        ft.Divider(),
                        ft.Text("Vendas por Categoria", size=20,
                                weight=ft.FontWeight.BOLD),
                        ft.Container(
                            content=criar_grafico_vendas(),
                            height=300,
                            padding=10
                        )
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                padding=20,
                expand=True
            )
        ],
        expand=True,
        scroll=ft.ScrollMode.AUTO
    )

    # Botões de navegação
    Botao_pagina_cadastro = ft.ElevatedButton(
        "Cadastrar Produtos",
        icon=ft.Icons.ADD_BOX,
        on_click=cadastrar_produto_pagina,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_700, 
            color=ft.Colors.WHITE, 
            padding=20
        ),
        height=100,
        width=300
    )

    botao_voltar = ft.ElevatedButton(
        "Voltar para Página Inicial",
        icon=ft.Icons.ARROW_BACK,
        on_click=voltar_pagina_inicial,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.GREY_700, 
            color=ft.Colors.WHITE,
            padding=10
        )
    )

    # ==============================================================
    # INICIALIZAÇÃO DA APLICAÇÃO
    # ==============================================================

    # Monta a página inicial
    page.add(header)
    page.add(ft.Row([
        ft.Column([secao_carrinho, form_busca], expand=2),
        ft.Column([Botao_pagina_cadastro], expand=1)
    ], expand=True))

    # Inicialização
    criar_banco()
    atualizar_tabela_produtos()
    atualizar_seletor_produtos()
    page.update()

# Configuração para Render
port = int(os.environ.get("PORT", 8000))

if __name__== "__main__":
    criar_banco()
ft.app(
    target=main,
    port=port,
    host="0.0.0.0",
    view=ft.WEB_BROWSER
)
