import asyncio
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import Image

from gui.service import scrape_targets
from models.product import NormalizedProduct

# =============================================================================
# Identidade Visual & Paleta ApexPrice Radar
# =============================================================================
COLOR_BG_DARK = "#121418"  # Fundo geral ultra-dark
COLOR_SURFACE = "#1A1D24"  # Painéis principais e cabeçalho
COLOR_CARD = "#21252E"  # Cartões de produtos e métricas
COLOR_CARD_HOVER = "#272C38"  # Hover de cartões
COLOR_ACCENT = "#FF6A2B"  # Laranja Radar Apex (Cor da logo)
COLOR_ACCENT_HOVER = "#E55518"  # Laranja escurecido para interação
COLOR_ACCENT_MUTED = "#FF8B57"  # Laranja suave para destaques secundários
COLOR_TEXT_PRIMARY = "#FFFFFF"  # Texto primário
COLOR_TEXT_MUTED = "#9CA3AF"  # Subtítulos e descrições
COLOR_BORDER = "#2B313D"  # Linhas divisórias e bordas
COLOR_GREEN_PRICE = "#10B981"  # Preços e descontos positivos
COLOR_AMAZON = "#D35400"  # Badge Amazon
COLOR_WORTEN = "#C0392B"  # Badge Worten

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


def get_asset_path(relative_path: str) -> Path:
    """Resolve o caminho de recursos tanto em desenvolvimento como congelado em PyInstaller."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / relative_path
    return Path(__file__).resolve().parent.parent / relative_path


class ApexPriceDesktopApp(ctk.CTk):
    """
    Interface Gráfica Desktop Moderna construída com CustomTkinter.
    Concebida com arquitetura multithreading não bloqueante, cartões de métricas,
    identidade visual ApexPrice Radar (Laranja Radar & Stealth Charcoal) e exportação executiva.
    """

    def __init__(self) -> None:
        super().__init__()

        # Configurações de Janela
        self.title("ApexPrice Radar - Desktop Price Intelligence")
        self.geometry("1060x720")
        self.minsize(940, 620)
        self.configure(fg_color=COLOR_BG_DARK)

        # Ícone da Janela (Windows Taskbar e Barra de Título)
        icon_path = get_asset_path("assets/logos/app_icon.ico")
        if icon_path.exists():
            import contextlib

            with contextlib.suppress(Exception):
                self.iconbitmap(str(icon_path))

        # Estado da Aplicação
        self.tracked_products: list[dict[str, str | float]] = []

        # Construção da Estrutura de Layout
        self._create_header_section()
        self._create_metrics_section()
        self._create_content_section()
        self._create_footer_section()

    def _create_header_section(self) -> None:
        """Painel Superior: Logótipo Oficial, Entrada de Pesquisa, Filtros e Ação."""
        header_frame = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=COLOR_SURFACE,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        header_frame.pack(fill="x", padx=20, pady=(16, 8))

        # Bloco de Topo: Logótipo e Descrição
        top_bar = ctk.CTkFrame(header_frame, fg_color="transparent")
        top_bar.pack(fill="x", padx=16, pady=(12, 10))

        # Tentativa de carregar a Logo Oficial renderizada
        logo_dark_path = get_asset_path("assets/logos/logo_dark.png")
        logo_light_path = get_asset_path("assets/logos/logo_light.png")

        if logo_dark_path.exists():
            try:
                pil_dark = Image.open(logo_dark_path)
                pil_light = (
                    Image.open(logo_light_path) if logo_light_path.exists() else pil_dark
                )
                self.logo_image = ctk.CTkImage(
                    light_image=pil_light, dark_image=pil_dark, size=(196, 56)
                )
                logo_label = ctk.CTkLabel(top_bar, image=self.logo_image, text="")
                logo_label.pack(side="left", padx=(0, 14))
            except Exception:
                self._fallback_text_logo(top_bar)
        else:
            self._fallback_text_logo(top_bar)

        # Tagline ao lado do Logo
        tagline_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        tagline_box.pack(side="left", fill="y", pady=(6, 0))

        ctk.CTkLabel(
            tagline_box,
            text="Price Intelligence & Automation Engine",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w")

        ctk.CTkLabel(
            tagline_box,
            text="Monitorização em tempo real de hardware, tecnologia e eletrónica (Worten & Amazon)",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w")

        # Linha de Controlos Interativos
        controls_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        controls_frame.pack(fill="x", padx=16, pady=(0, 14))

        # Campo de Entrada
        self.input_entry = ctk.CTkEntry(
            controls_frame,
            placeholder_text="Cole o URL (Worten/Amazon) ou digite um produto (ex.: MacBook Pro M4, PlayStation 5, Monitor 144Hz)...",
            height=44,
            font=ctk.CTkFont(size=13),
            fg_color="#14171D",
            border_color=COLOR_ACCENT,
            border_width=1,
            text_color=COLOR_TEXT_PRIMARY,
            placeholder_text_color="#6B7280",
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.input_entry.bind("<Return>", lambda _: self.on_track_button_clicked())

        # Dropdown de Loja
        self.store_dropdown = ctk.CTkOptionMenu(
            controls_frame,
            values=["Automático", "Amazon", "Worten"],
            width=125,
            height=44,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_CARD,
            button_color=COLOR_BORDER,
            button_hover_color=COLOR_ACCENT,
            dropdown_fg_color=COLOR_SURFACE,
            dropdown_hover_color=COLOR_ACCENT,
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.store_dropdown.set("Automático")
        self.store_dropdown.pack(side="left", padx=(0, 10))

        # Dropdown de Limite de Itens
        self.limit_dropdown = ctk.CTkOptionMenu(
            controls_frame,
            values=["25 Itens", "50 Itens", "100 Itens", "200 Itens", "500 Itens"],
            width=115,
            height=44,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_CARD,
            button_color=COLOR_BORDER,
            button_hover_color=COLOR_ACCENT,
            dropdown_fg_color=COLOR_SURFACE,
            dropdown_hover_color=COLOR_ACCENT,
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.limit_dropdown.set("100 Itens")
        self.limit_dropdown.pack(side="left", padx=(0, 10))

        # Botão de Ação Primária (Laranja Radar da Logo)
        self.track_button = ctk.CTkButton(
            controls_frame,
            text="Rastrear Produto",
            height=44,
            width=150,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self.on_track_button_clicked,
        )
        self.track_button.pack(side="left")

        # Barra de Progresso com destaque em Laranja
        self.progress_bar = ctk.CTkProgressBar(
            header_frame,
            height=3,
            fg_color="#14171D",
            progress_color=COLOR_ACCENT,
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 4))

    def _fallback_text_logo(self, parent: ctk.CTkFrame) -> None:
        """Fallback caso a imagem da logo não esteja presente no disco."""
        ctk.CTkLabel(
            parent,
            text="▲ ApexPrice RADAR",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLOR_ACCENT,
        ).pack(side="left", padx=(0, 12))

    def _create_metrics_section(self) -> None:
        """Painel de Métricas Rápidas: Cards com números de desempenho."""
        metrics_container = ctk.CTkFrame(self, fg_color="transparent")
        metrics_container.pack(fill="x", padx=20, pady=4)

        # Card 1: Total
        self.card_total, self.val_label_total = self._build_metric_card(
            metrics_container, title="PRODUTOS RASTREADOS", value="0", icon="📦", val_color=COLOR_TEXT_PRIMARY
        )
        self.card_total.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Card 2: Preço Médio
        self.card_avg, self.val_label_avg = self._build_metric_card(
            metrics_container, title="PREÇO MÉDIO", value="€ 0.00", icon="📊", val_color=COLOR_TEXT_PRIMARY
        )
        self.card_avg.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Card 3: Menor Preço (Destaque em Laranja Radar)
        self.card_min, self.val_label_min = self._build_metric_card(
            metrics_container, title="MENOR PREÇO (RADAR)", value="€ 0.00", icon="🎯", val_color=COLOR_ACCENT
        )
        self.card_min.pack(side="left", fill="x", expand=True)

    def _build_metric_card(
        self, parent: ctk.CTkFrame, title: str, value: str, icon: str, val_color: str = COLOR_TEXT_PRIMARY
    ) -> tuple[ctk.CTkFrame, ctk.CTkLabel]:
        card = ctk.CTkFrame(
            parent,
            corner_radius=10,
            fg_color=COLOR_CARD,
            border_width=1,
            border_color=COLOR_BORDER,
            height=72,
        )
        card.pack_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=8)

        ctk.CTkLabel(
            inner,
            text=f"{icon}  {title}",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w")

        val_label = ctk.CTkLabel(
            inner,
            text=value,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=val_color,
        )
        val_label.pack(anchor="w", pady=(2, 0))
        return card, val_label

    def _create_content_section(self) -> None:
        """Painel Central: Lista Dinâmica de Produtos Rasteados."""
        self.list_container = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color="#151820",
            border_width=1,
            border_color=COLOR_BORDER,
            label_text="Produtos Monitorizados na Sessão",
            label_font=ctk.CTkFont(size=13, weight="bold"),
            label_text_color=COLOR_TEXT_PRIMARY,
        )
        self.list_container.pack(fill="both", expand=True, padx=20, pady=10)

        # Placeholder quando vazio
        self.empty_label = ctk.CTkLabel(
            self.list_container,
            text="Nenhum produto rastreado ainda.\nCole um URL da Worten/Amazon ou termo de pesquisa acima.",
            font=ctk.CTkFont(size=14),
            text_color="#5D6574",
        )
        self.empty_label.pack(pady=80)

    def _create_footer_section(self) -> None:
        """Painel Inferior: Ações de Exportação, Limpeza e Barra de Estado."""
        footer_frame = ctk.CTkFrame(
            self,
            corner_radius=10,
            fg_color=COLOR_SURFACE,
            border_width=1,
            border_color=COLOR_BORDER,
            height=52,
        )
        footer_frame.pack(fill="x", padx=20, pady=(4, 16))

        # Status Bar à esquerda
        self.status_label = ctk.CTkLabel(
            footer_frame,
            text="🟢 Pronto para rastrear",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_MUTED,
        )
        self.status_label.pack(side="left", padx=16)

        # Botões de Ação à direita
        btn_box = ctk.CTkFrame(footer_frame, fg_color="transparent")
        btn_box.pack(side="right", padx=12, pady=8)

        self.btn_clear = ctk.CTkButton(
            btn_box,
            text="Limpar Lista",
            height=34,
            width=110,
            fg_color="#2A1C20",
            hover_color="#7F1D1D",
            text_color="#F87171",
            font=ctk.CTkFont(size=11),
            command=self.clear_history,
        )
        self.btn_clear.pack(side="left", padx=6)

        self.btn_export_csv = ctk.CTkButton(
            btn_box,
            text="Exportar CSV",
            height=34,
            width=115,
            fg_color=COLOR_CARD,
            hover_color=COLOR_CARD_HOVER,
            border_width=1,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            font=ctk.CTkFont(size=11),
            command=self.export_to_csv,
        )
        self.btn_export_csv.pack(side="left", padx=6)

        self.btn_export_excel = ctk.CTkButton(
            btn_box,
            text="Exportar Excel (.xlsx)",
            height=34,
            width=145,
            fg_color="#1E7145",
            hover_color="#165634",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.export_to_excel,
        )
        self.btn_export_excel.pack(side="left", padx=6)

    # -------------------------------------------------------------------------
    # Multi-Threading & Scraping Logic (Sem bloquear a interface)
    # -------------------------------------------------------------------------
    def on_track_button_clicked(self) -> None:
        raw_target = self.input_entry.get().strip()
        if not raw_target:
            messagebox.showwarning(
                "Campo Vazio", "Por favor, insira o URL do produto ou o nome do modelo."
            )
            return

        selected_store = self.store_dropdown.get()
        selected_limit_str = self.limit_dropdown.get()
        try:
            max_limit = int(selected_limit_str.split()[0])
        except (ValueError, IndexError):
            max_limit = 100

        self.track_button.configure(state="disabled", text="A extrair...")
        self.progress_bar.start()
        self.status_label.configure(
            text=f"🟠 A consultar dados ({selected_store}, até {max_limit} itens)...",
            text_color=COLOR_ACCENT,
        )

        worker = threading.Thread(
            target=self._scraping_worker_thread,
            args=(raw_target, selected_store, max_limit),
            daemon=True,
        )
        worker.start()

    def _scraping_worker_thread(
        self, target: str, store_preference: str, max_results: int = 100
    ) -> None:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            normalized_items: list[NormalizedProduct] = loop.run_until_complete(
                scrape_targets(target, store_preference, max_results=max_results)
            )
            loop.close()

            self.after(0, self._on_scraping_success, normalized_items, target)
        except Exception as exc:
            self.after(0, self._on_scraping_error, str(exc))

    def _on_scraping_success(
        self, products: list[NormalizedProduct], query_label: str
    ) -> None:
        self.progress_bar.stop()
        self.progress_bar.set(1.0)
        self.track_button.configure(state="normal", text="Rastrear Produto")

        if not products:
            self.status_label.configure(
                text="⚠️ Nenhum produto encontrado ou loja indisponível.",
                text_color="#F59E0B",
            )
            messagebox.showinfo(
                "Sem Resultados",
                f"Nenhum produto foi retornado para o termo/URL:\n{query_label}",
            )
            return

        new_items: list[dict[str, str | float]] = []
        for item in products:
            raw_name = (item.name or "").strip()
            if not raw_name or raw_name.lower() in ("none", "sem nome"):
                raw_name = f"Produto {item.retailer.value} ({item.sku})"

            product_dict: dict[str, str | float] = {
                "retailer": item.retailer.value,
                "sku": item.sku,
                "name": raw_name,
                "price": float(item.price),
                "url": item.url,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Evita duplicados exatos na tabela ativa
            is_dup = any(
                p["sku"] == product_dict["sku"]
                and p["retailer"] == product_dict["retailer"]
                for p in self.tracked_products
            ) or any(
                p["sku"] == product_dict["sku"]
                and p["retailer"] == product_dict["retailer"]
                for p in new_items
            )
            if not is_dup:
                new_items.append(product_dict)

        self.tracked_products = new_items + self.tracked_products
        self._render_items()
        self._update_metrics()

        self.status_label.configure(
            text=f"🟢 Sucesso: {len(new_items)} novo(s) produto(s) adicionado(s) à lista.",
            text_color="#10B981",
        )
        self.input_entry.delete(0, "end")

    def _on_scraping_error(self, error_msg: str) -> None:
        self.progress_bar.stop()
        self.progress_bar.set(0)
        self.track_button.configure(state="normal", text="Rastrear Produto")
        self.status_label.configure(
            text=f"❌ Erro de extração: {error_msg[:45]}...",
            text_color="#EF4444",
        )
        messagebox.showerror(
            "Erro de Scraping",
            f"Ocorreu uma falha durante a recolha dos dados:\n\n{error_msg}",
        )

    # -------------------------------------------------------------------------
    # Renderização da Tabela Dinâmica
    # -------------------------------------------------------------------------
    def _render_items(self) -> None:
        for widget in self.list_container.winfo_children():
            widget.destroy()

        if not self.tracked_products:
            self.empty_label = ctk.CTkLabel(
                self.list_container,
                text="Nenhum produto rastreado ainda.\nCole um URL ou termo acima para começar.",
                font=ctk.CTkFont(size=14),
                text_color="#5D6574",
            )
            self.empty_label.pack(pady=80)
            return

        for idx, item in enumerate(self.tracked_products):
            self._create_product_card(idx, item)

    def _create_product_card(self, index: int, item: dict[str, str | float]) -> None:
        card = ctk.CTkFrame(
            self.list_container,
            corner_radius=10,
            fg_color=COLOR_CARD,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        card.pack(fill="x", pady=4, padx=4)

        # 1. Elementos da DIREITA (Empacotados primeiro para prioridade de layout)
        btn_del = ctk.CTkButton(
            card,
            text="✕",
            width=32,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2A1B1E",
            hover_color="#DC2626",
            text_color="#F87171",
            command=lambda idx=index: self._delete_item(idx),
        )
        btn_del.pack(side="right", padx=(4, 12), pady=8)

        target_url = str(item.get("url", "")).strip()
        if target_url:
            btn_open = ctk.CTkButton(
                card,
                text="Ver Oferta ↗",
                width=92,
                height=32,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#181B20",
                hover_color=COLOR_ACCENT,
                text_color=COLOR_TEXT_PRIMARY,
                command=lambda u=target_url: webbrowser.open(u),
            )
            btn_open.pack(side="right", padx=4, pady=8)

        price_val = float(item.get("price", 0.0))
        price_lbl = ctk.CTkLabel(
            card,
            text=f"€ {price_val:.2f}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLOR_GREEN_PRICE,
        )
        price_lbl.pack(side="right", padx=16, pady=8)

        # 2. Elementos da ESQUERDA (Badge da loja)
        retailer = str(item.get("retailer", "LOJA"))
        badge_color = COLOR_AMAZON if "AMAZON" in retailer else COLOR_WORTEN
        badge = ctk.CTkLabel(
            card,
            text=f" {retailer} ",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=badge_color,
            corner_radius=6,
            text_color="#FFFFFF",
        )
        badge.pack(side="left", padx=12, pady=10)

        # 3. Informações Centrais (Ocupa todo o espaço restante sem colidir)
        info_box = ctk.CTkFrame(card, fg_color="transparent")
        info_box.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        raw_name = str(item.get("name") or "").strip()
        if not raw_name or raw_name.lower() in ("none", "sem nome"):
            raw_name = f"Produto {retailer} ({item.get('sku', 'N/D')})"
        display_name = raw_name if len(raw_name) <= 72 else raw_name[:69] + "..."

        name_lbl = ctk.CTkLabel(
            info_box,
            text=display_name,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
            justify="left",
        )
        name_lbl.pack(fill="x", anchor="w")

        sku_val = str(item.get("sku") or "N/D")
        time_val = str(item.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        meta_lbl = ctk.CTkLabel(
            info_box,
            text=f"SKU: {sku_val} | Registado em: {time_val}",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
            justify="left",
        )
        meta_lbl.pack(fill="x", anchor="w", pady=(2, 0))

    def _delete_item(self, index: int) -> None:
        if 0 <= index < len(self.tracked_products):
            removed = self.tracked_products.pop(index)
            self._render_items()
            self._update_metrics()
            self.status_label.configure(
                text=f"Item removido: {str(removed['name'])[:30]}...",
                text_color=COLOR_TEXT_MUTED,
            )

    def _update_metrics(self) -> None:
        total = len(self.tracked_products)
        self.val_label_total.configure(text=str(total))

        if total > 0:
            prices = [float(p.get("price", 0.0)) for p in self.tracked_products]
            avg_price = sum(prices) / total
            min_price = min(prices)
            self.val_label_avg.configure(text=f"€ {avg_price:.2f}")
            self.val_label_min.configure(text=f"€ {min_price:.2f}")
        else:
            self.val_label_avg.configure(text="€ 0.00")
            self.val_label_min.configure(text="€ 0.00")

    def clear_history(self) -> None:
        if not self.tracked_products:
            return
        if messagebox.askyesno("Limpar Histórico", "Deseja remover todos os itens da lista?"):
            self.tracked_products.clear()
            self._render_items()
            self._update_metrics()
            self.status_label.configure(text="Histórico limpo.", text_color=COLOR_TEXT_MUTED)

    # -------------------------------------------------------------------------
    # Exportação (CSV e Excel)
    # -------------------------------------------------------------------------
    def export_to_csv(self) -> None:
        if not self.tracked_products:
            messagebox.showinfo("Exportar", "Não há produtos na lista para exportar.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Ficheiros CSV", "*.csv")],
            initialfile=f"produtos_rastreados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not file_path:
            return

        try:
            df = pd.DataFrame(self.tracked_products)
            df.to_csv(file_path, index=False, encoding="utf-8-sig")
            messagebox.showinfo("Exportado com Sucesso", f"Ficheiro guardado em:\n{file_path}")
            self.status_label.configure(text="Ficheiro CSV exportado com sucesso.")
        except Exception as exc:
            messagebox.showerror("Erro de Exportação", f"Falha ao exportar CSV:\n{exc}")

    def export_to_excel(self) -> None:
        if not self.tracked_products:
            messagebox.showinfo("Exportar", "Não há produtos na lista para exportar.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Microsoft Excel", "*.xlsx")],
            initialfile=f"relatorio_desktop_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        )
        if not file_path:
            return

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            if ws is None:
                ws = wb.create_sheet()

            ws.title = "Produtos Rastreados"
            ws.views.sheetView[0].showGridLines = True

            # Cabeçalho corporativo estilizado com Apex Coral/Navy
            header_fill = PatternFill(start_color="1B1D23", end_color="1B1D23", fill_type="solid")
            header_font = Font(name="Segoe UI", size=11, bold=True, color="FF6A2B")
            border = Border(
                left=Side(style="thin", color="D9D9D9"),
                right=Side(style="thin", color="D9D9D9"),
                top=Side(style="thin", color="D9D9D9"),
                bottom=Side(style="thin", color="D9D9D9"),
            )

            headers = ["Loja", "SKU", "Nome do Produto", "Preço (€)", "Data Consulta", "URL"]
            ws.append(headers)

            for col_idx in range(1, len(headers) + 1):
                c = ws.cell(row=1, column=col_idx)
                c.fill = header_fill
                c.font = header_font
                c.alignment = Alignment(horizontal="center", vertical="center")

            for item in self.tracked_products:
                row_vals = [
                    str(item.get("retailer")),
                    str(item.get("sku")),
                    str(item.get("name")),
                    float(item.get("price", 0.0)),
                    str(item.get("timestamp")),
                    str(item.get("url")),
                ]
                ws.append(row_vals)
                curr_row = ws.max_row
                ws.cell(row=curr_row, column=4).number_format = '"€" #,##0.00'
                for c_i in range(1, len(row_vals) + 1):
                    ws.cell(row=curr_row, column=c_i).border = border

            # Ajuste dinâmico de largura de coluna
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_idx = col[0].column
                if not isinstance(col_idx, int):
                    continue
                col_letter = get_column_letter(col_idx)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 60)

            wb.save(file_path)
            messagebox.showinfo("Exportado com Sucesso", f"Relatório Excel guardado:\n{file_path}")
            self.status_label.configure(text="Relatório Excel exportado com sucesso.")
        except Exception as exc:
            messagebox.showerror("Erro de Exportação", f"Falha ao exportar Excel:\n{exc}")


def launch_gui() -> None:
    app = ApexPriceDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
