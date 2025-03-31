import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Diagnostické výpisy
print("="*50)
print("Diagnostické informácie:")
print(f"Aktuálny pracovný priečinok: {os.getcwd()}")
print(f"Absolútna cesta k skriptu: {os.path.abspath(__file__)}")
print("Obsah aktuálneho priečinka:")
for item in os.listdir():
    print(f"  - {item}")
print("="*50)

import telebot
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict
from dataclasses import dataclass
import math
import io
from datetime import datetime
import re
import logging
import sys
import os
import time
from decimal import Decimal
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Konfigurácia
TOKEN = '8177519675:AAE1xLZEyODePjcYC2RlaG7xf2QUCa2aSiE'
STOCK_WIDTH = 321
STOCK_HEIGHT = 225

# Nastavenie absolútnej cesty k databáze
DB_PATH = '/home22/server/rezaciautocad/glass_calculator.db'

# SQLAlchemy setup
Base = declarative_base()
engine = create_engine(f'sqlite:///{DB_PATH}')
Session = sessionmaker(bind=engine)

# Database models
class GlassCategory(Base):
    __tablename__ = 'glass_categories'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    glasses = relationship("Glass", back_populates="category")

class Glass(Base):
    __tablename__ = 'glasses'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    category_id = Column(Integer, ForeignKey('glass_categories.id'))
    price_per_m2 = Column(Float, nullable=False)
    cutting_fee = Column(Float, nullable=False)
    min_area = Column(Float, nullable=False)
    
    category = relationship("GlassCategory", back_populates="glasses")

class Calculation(Base):
    __tablename__ = 'calculations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    glass_id = Column(Integer, ForeignKey('glasses.id'))
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    area = Column(Float, nullable=False)
    waste_area = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Vytvorenie tabuliek
Base.metadata.create_all(engine)

def setup_logging():
    if not os.path.exists('logs'):
        os.makedirs('logs')

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(f'logs/bot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    telebot_logger = logging.getLogger('telebot')
    telebot_logger.setLevel(logging.DEBUG)
    
    logging.info('Logovanie inicializované')

@dataclass
class GlassPanel:
    width: float
    height: float
    thickness: float
    rotated: bool = False
    
    def get_dimensions(self) -> Tuple[float, float]:
        return (self.height, self.width) if self.rotated else (self.width, self.height)
    
    def rotate(self):
        self.rotated = not self.rotated
        return self

class GlassCalculator:
    def __init__(self, session, user_states=None):
        self.session = session
        self.user_states = user_states

    def get_glass_price(self, glass_id: int, width: float, height: float, chat_id: int) -> Dict:
        glass = self.session.query(Glass).get(glass_id)
        area = (width * height) / 1000000  # Convert to m²
        
        # Získanie odpadu z user_states pre konkrétneho užívateľa
        if self.user_states and chat_id in self.user_states:
            waste_percentage = self.user_states[chat_id].get('total_waste', 0) / 100
        else:
            waste_percentage = 0
            
        waste_area = area * waste_percentage  # Plocha odpadu
        
        # Cena za užitočnú plochu
        if area < glass.min_area:
            area = glass.min_area
        base_price = area * glass.price_per_m2
        
        # Cena za odpad
        waste_price = waste_area * glass.price_per_m2
        
        return {
            'glass_name': glass.name,
            'dimensions': f"{width}x{height}mm",
            'area': round(area, 2),
            'area_price': round(base_price, 2),
            'waste_area': round(waste_area, 2),
            'waste_price': round(waste_price, 2)
        }

class CuttingOptimizer:
    def __init__(self, stock_width: float, stock_height: float):
        self.stock_width = stock_width
        self.stock_height = stock_height
        self.min_gap = 0.2
        logging.info(f'Inicializovaný CuttingOptimizer s rozmermi {stock_width}x{stock_height}')

    def optimize_multiple_sheets(self, panels: List[GlassPanel]) -> List[Tuple[List[Tuple[float, float, float, float, bool]], float]]:
        remaining_panels = panels.copy()
        all_layouts = []
        sheet_number = 1
        
        while remaining_panels:
            logging.info(f'Optimalizujem tabuľu #{sheet_number} s {len(remaining_panels)} panelmi')
            
            layout, waste = self.optimize(remaining_panels)
            
            if not layout:
                successful_panels = []
                failed_panels = []
                
                for panel in remaining_panels:
                    test_layout, test_waste = self.optimize(successful_panels + [panel])
                    if test_layout:
                        successful_panels.append(panel)
                    else:
                        failed_panels.append(panel)
                
                if successful_panels:
                    layout, waste = self.optimize(successful_panels)
                    all_layouts.append((layout, waste))
                    remaining_panels = failed_panels
                    sheet_number += 1
                else:
                    logging.error(f'Nepodarilo sa umiestniť panel {failed_panels[0].width}x{failed_panels[0].height}')
                    break
            else:
                all_layouts.append((layout, waste))
                break
        
        return all_layouts

    def optimize(self, panels: List[GlassPanel]) -> Tuple[List[Tuple[float, float, float, float, bool]], float]:
        logging.info(f'Začiatok optimalizácie pre {len(panels)} panelov')
        best_layout = []
        best_waste = float('inf')
        start_time = time.time()
        MAX_TIME = 30
        
        sorting_strategies = [
            lambda p: (-max(p.width, p.height)),
            lambda p: (-p.width * p.height),
            lambda p: (-min(p.width, p.height)),
            lambda p: (-(p.width + p.height)),
        ]
        
        if len(panels) > 8:
            rotation_patterns = [0]
        elif len(panels) > 6:
            rotation_patterns = range(0, 2 ** len(panels), 4)
        else:
            rotation_patterns = range(2 ** len(panels))
            
        corners = ['bottom-left'] if len(panels) > 6 else ['bottom-left', 'bottom-right', 'top-left', 'top-right']
        
        for strategy_index, sort_key in enumerate(sorting_strategies):
            if time.time() - start_time > MAX_TIME:
                break
                
            for start_corner in corners:
                for rotation_pattern in rotation_patterns:
                    if time.time() - start_time > MAX_TIME:
                        break
                        
                    current_panels = panels.copy()
                    
                    for i, panel in enumerate(current_panels):
                        if rotation_pattern & (1 << i):
                            panel.rotate()
                    
                    sorted_panels = sorted(current_panels, key=sort_key)
                    layout = self._place_panels_enhanced(sorted_panels, start_corner)
                    
                    if layout:
                        if self._check_overlap(layout):
                            continue
                            
                        waste = self._calculate_waste(layout)
                        if waste < best_waste:
                            best_waste = waste
                            best_layout = layout
                            
                            if waste < 15:
                                return best_layout, best_waste
        
        return best_layout, best_waste

    def calculate_total_area(self, panels: List[GlassPanel]) -> float:
        return sum(panel.width * panel.height for panel in panels) / 10000

    def calculate_waste_area(self, total_panels_area: float) -> float:
        stock_area = (self.stock_width * self.stock_height) / 10000
        return stock_area - total_panels_area

    def _calculate_waste(self, layout: List[Tuple[float, float, float, float, bool]]) -> float:
        used_area = sum(width * height for _, _, width, height, _ in layout)
        total_area = self.stock_width * self.stock_height
        return ((total_area - used_area) / total_area) * 100

    def visualize(self, layout: List[Tuple[float, float, float, float, bool]]) -> io.BytesIO:
        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(111)
        
        ax.add_patch(plt.Rectangle((0, 0), self.stock_width, self.stock_height, 
                                 fill=False, color='black', linewidth=2))
        
        colors = ['lightblue', 'lightgreen', 'lightpink', 'lightyellow']
        for i, (x, y, w, h, rotated) in enumerate(layout):
            color = colors[i % len(colors)]
            ax.add_patch(plt.Rectangle((x, y), w, h, fill=True, color=color))
            ax.text(x + w/2, y + h/2, 
                   f'{w:.1f}x{h:.1f}\n{"(R)" if rotated else ""}',
                   horizontalalignment='center',
                   verticalalignment='center',
                   fontsize=8)
        
        ax.set_xlim(-10, self.stock_width + 10)
        ax.set_ylim(-10, self.stock_height + 10)
        ax.set_aspect('equal')
        plt.title(f'Optimalizovan rozloženie panelov\n{datetime.now().strftime("%Y-%m-%d %H:%M")}')
        plt.grid(True)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        
        plt.close(fig)
        
        return buf

    def _place_panels_enhanced(self, panels: List[GlassPanel], start_corner: str) -> List[Tuple[float, float, float, float, bool]]:
        layout = []
        
        if start_corner == 'bottom-left':
            spaces = [(0, 0, self.stock_width, self.stock_height)]
        elif start_corner == 'bottom-right':
            spaces = [(self.stock_width, 0, -self.stock_width, self.stock_height)]
        elif start_corner == 'top-left':
            spaces = [(0, self.stock_height, self.stock_width, -self.stock_height)]
        else:  # top-right
            spaces = [(self.stock_width, self.stock_height, -self.stock_width, -self.stock_height)]

        for i, panel in enumerate(panels):
            width, height = panel.get_dimensions()
            placed = False
            
            for space_index, (space_x, space_y, space_width, space_height) in enumerate(spaces):
                if width <= abs(space_width) and height <= abs(space_height):
                    if start_corner == 'bottom-left':
                        x, y = space_x, space_y
                    elif start_corner == 'bottom-right':
                        x, y = space_x - width, space_y
                    elif start_corner == 'top-left':
                        x, y = space_x, space_y - height
                    else:  # top-right
                        x, y = space_x - width, space_y - height
                    
                    layout.append((x, y, width, height, panel.rotated))
                    placed = True
                    
                    new_spaces = []
                    if abs(space_width) - width > 0:
                        new_spaces.append((
                            x + (width if start_corner in ['bottom-left', 'top-left'] else -width),
                            space_y,
                            space_width - (width if start_corner in ['bottom-left', 'top-left'] else -width),
                            height
                        ))
                    if abs(space_height) - height > 0:
                        new_spaces.append((
                            space_x,
                            y + (height if start_corner in ['bottom-left', 'bottom-right'] else -height),
                            space_width,
                            space_height - (height if start_corner in ['bottom-left', 'bottom-right'] else -height)
                        ))
                    
                    spaces = spaces[:space_index] + spaces[space_index+1:] + new_spaces
                    break
            
            if not placed:
                return []
        
        return layout

    def _check_overlap(self, layout: List[Tuple[float, float, float, float, bool]]) -> bool:
        for i, (x, y, w, h, rotated) in enumerate(layout):
            for j in range(i + 1, len(layout)):
                x2, y2, w2, h2, rotated2 = layout[j]
                if rotated != rotated2:
                    continue
                
                if rotated:
                    x2, y2 = x2 + w2, y2 + h2
                    w2, h2 = h2, w2
                
                if x < x2 + w2 and x + w > x2 and y < y2 + h2 and y + h > y2:
                    return True
        
        return False

class GlassCuttingBot:
    def __init__(self, token: str):
        logging.info('Inicializcia GlassCuttingBot')
        self.bot = telebot.TeleBot(token)
        self.user_dimensions = {}
        self.optimizer = None
        self.user_states = {}
        self.calculator = GlassCalculator(Session(), self.user_states)
        
        try:
            self.bot.remove_webhook()
            time.sleep(0.5)
            logging.info('Webhook úspešne odstránený')
        except Exception as e:
            logging.warning(f'Chyba pri odstraňovaní webhoku: {e}')
            
        self.STATES = {
            'WAITING_FOR_DIMENSIONS': 1,
            'WAITING_FOR_GLASS_TYPE': 2,
            'WAITING_FOR_CONFIRMATION': 3
        }
        
        self.setup_handlers()
        logging.info('GlassCuttingBot inicializovaný')

    def setup_handlers(self):
        @self.bot.message_handler(commands=['start'])
        def start(message):
            markup = telebot.types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
            btn1 = telebot.types.KeyboardButton('321 x 225 cm')
            btn2 = telebot.types.KeyboardButton('160.5 x 255 cm')
            markup.add(btn1, btn2)
            
            welcome_text = (
                "Vitajte v optimalizátore rezania a kalkul��tore cien skla!\n\n"
                "Dostupné príkazy:\n"
                "/start - Spustí nový výpočet\n"
                "/help - Zobrazí návod na použitie\n"
                "/history - Zobrazí históriu kalkuláci\n"
                "/clear_history - Vymaže históriu kalkulácií\n\n"
                "Najprv si prosím vyberte rozmer tabule:"
            )
            self.bot.reply_to(message, welcome_text, reply_markup=markup)

        @self.bot.message_handler(func=lambda message: message.text in ['321 x 225 cm', '160.5 x 255 cm'])
        def handle_dimension_choice(message):
            if message.text == '321 x 225 cm':
                width, height = 321, 225
            else:
                width, height = 160.5, 255
            
            self.user_dimensions[message.chat.id] = (width, height)
            self.optimizer = CuttingOptimizer(width, height)
            
            response_text = (
                f"✅ Vybrali ste rozmer: {width}x{height} cm\n\n"
                "Teraz zadajte rozmery skiel v jednom z formátov:\n"
                "1️⃣ Jeden rozmer: 100x50 alebo 83.5x92.2\n"
                "2️⃣ Viac rozmerov naraz: 100x50-200x30-80.5x90.2\n"
            )
            self.bot.reply_to(message, response_text)
            self.user_states[message.chat.id] = self.STATES['WAITING_FOR_DIMENSIONS']

        @self.bot.message_handler(func=lambda message: 
            message.chat.id in self.user_states and 
            self.user_states[message.chat.id] == self.STATES['WAITING_FOR_DIMENSIONS'])
        def handle_glass_dimensions(message):
            try:
                dimensions = self.parse_dimensions(message.text)
                if not dimensions:
                    self.bot.reply_to(message, "❌ Nesprávny formát rozmerov!")
                    return

                panels = []
                for width, height in dimensions:
                    if self.validate_dimensions(width, height, message.chat.id):
                        panels.append(GlassPanel(width, height, 4.0))

                if not panels:
                    self.bot.reply_to(message, "❌ Žiadne platné rozmery!")
                    return

                # Výpoet optimálneho rozloženia
                processing_msg = self.bot.reply_to(message, "🔄 Prebieha výpočet optimálneho rozloženia...")
                
                all_layouts = self.optimizer.optimize_multiple_sheets(panels)
                if not all_layouts:
                    self.bot.reply_to(message, "❌ Nepodarilo sa nájsť vhodné rozloženie.")
                    return

                # Výpočet total_waste pred jeho použitím
                total_waste = 0
                for sheet_index, (layout, waste) in enumerate(all_layouts, 1):
                    img_buf = self.optimizer.visualize(layout)
                    sheet_area = sum(width * height / 10000 for _, _, width, height, _ in layout)
                    waste_area = self.optimizer.calculate_waste_area(sheet_area)

                    caption = (
                        f"📋 Tabula #{sheet_index}\n"
                        f"📏 Plocha skiel: {sheet_area:.2f} m²\n"
                        f"🗑️ Odpad: {waste_area:.2f} m²\n"
                        f"📊 Využitie: {100-waste:.1f}%"
                    )
                    
                    self.bot.send_photo(message.chat.id, img_buf, caption=caption)
                    total_waste += waste

                # Uloženie výsledkov pre neskoršie použitie
                self.user_states[message.chat.id] = {
                    'layouts': all_layouts,
                    'total_area': sum(panel.width * panel.height / 10000 for panel in panels),
                    'panels': panels,
                    'total_waste': total_waste
                }

                # Výpočet priemerného odpadu
                if len(all_layouts) > 0:
                    average_waste = total_waste/len(all_layouts)
                else:
                    average_waste = 0

                # Zobrazenie súhrnných informácií s tlačidlami
                markup = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
                btn_yes = telebot.types.KeyboardButton('Áno')
                btn_no = telebot.types.KeyboardButton('Nie') 
                markup.add(btn_yes, btn_no)

                summary = (
                    f"📊 Celkový súhrn:\n"
                    f"📦 Počet tabúľ: {len(all_layouts)}\n"
                    f"📏 Celková plocha skiel: {self.user_states[message.chat.id]['total_area']:.2f} m²\n"
                    f"🗑️ Priemerný odpad: {average_waste:.1f}%\n\n"
                    "Chcete pokračovať s výpočtom ceny?"
                )
                
                # Uložíme stav pred odoslaním správy
                self.user_states[message.chat.id] = {
                    'layouts': all_layouts,
                    'total_area': self.user_states[message.chat.id]['total_area'],
                    'panels': panels,
                    'total_waste': total_waste,
                    'state': self.STATES['WAITING_FOR_GLASS_TYPE']
                }
                
                self.bot.reply_to(message, summary, reply_markup=markup)

            except Exception as e:
                logging.error(f"Chyba pri spracovaní rozmerov: {str(e)}", exc_info=True)
                self.bot.reply_to(message, f" Nastala chyba: {str(e)}")

        @self.bot.message_handler(func=lambda message: 
            message.chat.id in self.user_states and 
            isinstance(self.user_states[message.chat.id], dict) and
            self.user_states[message.chat.id].get('state') == self.STATES['WAITING_FOR_GLASS_TYPE'] and
            message.text == 'Áno')
        def handle_glass_type_selection(message):
            try:
                logging.info(f"Spracovávam odpoveď Áno od užívateľa {message.chat.id}")
                # Získanie kategórií skla z databázy
                session = Session()
                categories = session.query(GlassCategory).all()
                
                if not categories:
                    self.bot.reply_to(message, "❌ V databáze nie sú žiadne kategórie skla.")
                    return
                
                markup = telebot.types.InlineKeyboardMarkup()
                for category in categories:
                    callback_data = f"cat_{category.id}"
                    logging.info(f"Pridávam kategóriu: {category.name} s callback_data: {callback_data}")
                    markup.add(telebot.types.InlineKeyboardButton(
                        category.name,
                        callback_data=callback_data
                    ))
                
                # Odstránime klávesnicu s Áno/Nie
                remove_markup = telebot.types.ReplyKeyboardRemove()
                
                self.bot.reply_to(
                    message,
                    "Vyberte kategóriu skla:",
                    reply_markup=markup
                )
                
                # Aktualizujeme stav
                self.user_states[message.chat.id]['state'] = 'selecting_category'
                
            except Exception as e:
                logging.error(f"Chyba pri výbere kategórie skla: {str(e)}", exc_info=True)
                self.bot.reply_to(message, "❌ Nastala chyba pri výbere kategórie skla")
            finally:
                session.close()

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_'))
        def handle_category_selection(call):
            category_id = int(call.data.split('_')[1])
            
            session = Session()
            glasses = session.query(Glass).filter_by(category_id=category_id).all()
            
            markup = telebot.types.InlineKeyboardMarkup()
            for glass in glasses:
                markup.add(telebot.types.InlineKeyboardButton(
                    f"{glass.name} ({glass.price_per_m2}€/m²)",
                    callback_data=f"glass_{glass.id}"
                ))
            
            self.bot.edit_message_text(
                "Vyberte typ skla:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('glass_'))
        def handle_glass_selection(call):
            try:
                session = Session()
                glass_id = int(call.data.split('_')[1])
                chat_id = call.message.chat.id
                
                logging.info(f"Spracovávam výber skla: glass_id={glass_id}, chat_id={chat_id}")
                
                if chat_id not in self.user_states:
                    logging.error(f"Chat ID {chat_id} nemá uložený stav")
                    self.bot.answer_callback_query(call.id, "❌ Chyba: Začnite znova príkazom /start")
                    return

                if not isinstance(self.user_states[chat_id], dict):
                    logging.error(f"Nesprávny formát user_states pre chat_id {chat_id}")
                    self.bot.answer_callback_query(call.id, "❌ Chyba: Začnite znova príkazom /start")
                    return

                if 'total_area' not in self.user_states[chat_id]:
                    logging.error(f"Chýba total_area pre chat_id {chat_id}")
                    self.bot.answer_callback_query(call.id, "❌ Chyba: Začnite znova príkazom /start")
                    return

                # Výpočet ceny
                total_area = self.user_states[chat_id]['total_area']
                logging.info(f"Počítam cenu pre plochu {total_area}m²")
                
                glass = session.query(Glass).get(glass_id)
                if not glass:
                    logging.error(f"Sklo s ID {glass_id} nebolo nájdené")
                    self.bot.answer_callback_query(call.id, "❌ Chyba: Sklo nebolo nájdené")
                    return

                price_calculation = self.calculator.get_glass_price(glass_id, total_area * 1000, 1000, chat_id)
                
                summary = (
                    f"💰 Cenová kalkulácia:\n\n"
                    f"Typ skla: {price_calculation['glass_name']}\n"
                    f"Plocha skiel: {price_calculation['area']:.2f} m² = {price_calculation['area_price']}€\n"
                    f"Plocha odpadu: {price_calculation['waste_area']:.2f} m² = {price_calculation['waste_price']}€\n"
                )
                
                logging.info(f"Odosielam cenovú kalkuláciu pre chat_id {chat_id}")
                
                # Najprv potvrďte callback query
                self.bot.answer_callback_query(call.id)
                
                # Potom upravte správu
                self.bot.edit_message_text(
                    summary,
                    chat_id,
                    call.message.message_id
                )
                
                # Pridáme tlačidlo na generovanie PDF
                markup = telebot.types.InlineKeyboardMarkup()
                markup.add(telebot.types.InlineKeyboardButton(
                    "📄 Generovať PDF",
                    callback_data=f"pdf_{glass_id}"
                ))
                
                self.bot.send_message(
                    chat_id,
                    "Chcete vygenerovať PDF s výkresom a cenovou kalkuláciou?",
                    reply_markup=markup
                )
                
            except Exception as e:
                logging.error(f"Kritická chyba pri spracovaní výberu skla: {str(e)}", exc_info=True)
                try:
                    self.bot.answer_callback_query(call.id, "❌ Nastala chyba pri výpočte")
                    self.bot.send_message(chat_id, "❌ Nastala chyba. Prosím, začnite znova príkazom /start")
                except:
                    pass
            finally:
                session.close()

        @self.bot.message_handler(func=lambda message: 
            message.chat.id in self.user_states and 
            self.user_states[message.chat.id] == self.STATES['WAITING_FOR_GLASS_TYPE'] and
            message.text in ['Nie'])
        def handle_no_price_calculation(message):
            self.user_states[message.chat.id] = self.STATES['WAITING_FOR_DIMENSIONS']
            markup = telebot.types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
            btn1 = telebot.types.KeyboardButton('321 x 225 cm')
            btn2 = telebot.types.KeyboardButton('160.5 x 255 cm')
            markup.add(btn1, btn2)
            self.bot.reply_to(
                message,
                "✅ V poriadku. Pre novú kalkuláciu vyberte rozmer tabule:",
                reply_markup=markup
            )

        @self.bot.message_handler(commands=['help'])
        def help(message):
            help_text = (
                "📋 Návod na použitie:\n\n"
                "1⃣ /start - Spustí nový výpočet\n"
                "2️ Vyberte rozmer tabule\n"
                "3️⃣ Zadajte rozmery skiel:\n"
                "   • Jeden rozmer: 100x50\n"
                "   • Viac rozmerov: 100x50-200x30\n"
                "4️⃣ Potvrďte výpočet ceny\n"
                "5️⃣ Vyberte typ skla\n\n"
                "Ďalšie príkazy:\n"
                "/history - Zobrazí históriu kalkulácií\n"
                "/clear_history - Vymaze históriu kalkulácií\n\n"
                "❓ Pre ďalšiu pomoc kontaktujte administrátora"
            )
            self.bot.reply_to(message, help_text)

        @self.bot.message_handler(commands=['clear_history'])
        def clear_history(message):
            try:
                session = Session()
                session.query(Calculation).filter_by(user_id=message.chat.id).delete()
                session.commit()
                self.bot.reply_to(message, "✅ História kalkulácií bola vymazaná")
            except Exception as e:
                logging.error(f"Chyba pri mazaní histórie: {str(e)}")
                self.bot.reply_to(message, "❌ Nastala chyba pri mazaní histórie")

        @self.bot.message_handler(commands=['history'])
        def show_history(message):
            try:
                session = Session()
                calculations = session.query(Calculation).filter_by(user_id=message.chat.id).order_by(Calculation.created_at.desc()).limit(5).all()
                
                if not calculations:
                    self.bot.reply_to(message, "Zatiaľ nemáte žiadne kalkulácie")
                    return
                    
                history_text = "📋 Posledných 5 kalkulácií:\n\n"
                for calc in calculations:
                    glass = session.query(Glass).get(calc.glass_id)
                    history_text += (
                        f"🕒 {calc.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                        f"📏 Plocha: {calc.area:.2f} m²\n"
                        f"🗑️ Odpad: {calc.waste_area:.2f} m²\n"
                        f"💰 Cena: {calc.total_price}€\n"
                        f"🪟 Typ: {glass.name}\n\n"
                    )
                    
                self.bot.reply_to(message, history_text)
            except Exception as e:
                logging.error(f"Chyba pri zobrazení histórie: {str(e)}")
                self.bot.reply_to(message, "❌ Nastala chyba pri načítaní histórie")

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('pdf_'))
        def handle_pdf_generation(call):
            try:
                chat_id = call.message.chat.id
                glass_id = int(call.data.split('_')[1])
                
                # Získanie potrebných dát
                if chat_id not in self.user_states:
                    self.bot.answer_callback_query(call.id, "❌ Chyba: Začnite znova príkazom /start")
                    return
                
                # Generovanie PDF
                pdf_buffer = self.generate_pdf(chat_id, glass_id)
                
                # Odoslanie PDF
                self.bot.send_document(
                    chat_id,
                    ('kalkulacia.pdf', pdf_buffer),
                    caption="📄 Vaša kalkulácia v PDF"
                )
                
                self.bot.answer_callback_query(call.id)
                
            except Exception as e:
                logging.error(f"Chyba pri generovaní PDF: {str(e)}", exc_info=True)
                self.bot.answer_callback_query(call.id, "❌ Chyba pri generovaní PDF")

    def parse_dimensions(self, text: str) -> List[Tuple[float, float]]:
        dimensions = []
        text = text.replace(',', '.').replace(' ', '')
        parts = text.split('-')
        
        for part in parts:
            match = re.match(r'(\d+\.?\d*)x(\d+\.?\d*)', part.lower())
            if match:
                width, height = map(float, match.groups())
                dimensions.append((width, height))
    
        return dimensions

    def validate_dimensions(self, width: float, height: float, chat_id: int) -> bool:
        if width <= 0 or height <= 0:
            return False
        
        stock_width, stock_height = self.user_dimensions.get(chat_id, (STOCK_WIDTH, STOCK_HEIGHT))
        valid = (width <= stock_width and height <= stock_height) or \
                (height <= stock_width and width <= stock_height)
        
        return valid

    def run(self):
        """Spustenie bota."""
        try:
            self.bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            logging.error(f"Chyba pri behu bota: {str(e)}", exc_info=True)
            raise e

    def generate_pdf(self, chat_id: int, glass_id: int) -> io.BytesIO:
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        try:
            # Vytvorenie novej session pre túto operáciu
            session = Session()
            
            # Získanie dát
            glass = session.query(Glass).get(glass_id)
            layouts = self.user_states[chat_id]['layouts']
            
            # Vytvorenie novej inštancie kalkulátora s novou session
            calculator = GlassCalculator(session, self.user_states)
            price_calculation = calculator.get_glass_price(
                glass_id, 
                self.user_states[chat_id]['total_area'] * 1000, 
                1000, 
                chat_id
            )
            
            # Hlavička
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, height - 50, "Kalkulácia skla")
            
            # Informácie o skle
            c.setFont("Helvetica", 12)
            y = height - 100
            c.drawString(50, y, f"Typ skla: {glass.name}")
            y -= 20
            c.drawString(50, y, f"Plocha skiel: {price_calculation['area']:.2f} m² = {price_calculation['area_price']}€")
            y -= 20
            c.drawString(50, y, f"Plocha odpadu: {price_calculation['waste_area']:.2f} m² = {price_calculation['waste_price']}€")
            
            # Pridanie výkresu
            y -= 50
            for i, (layout, waste) in enumerate(layouts):
                img_buf = self.optimizer.visualize(layout)
                img_reader = ImageReader(img_buf)
                c.drawImage(img_reader, 50, y - 300, width=400, height=300)
                y -= 320
            
            c.save()
            buffer.seek(0)
            return buffer
            
        except Exception as e:
            logging.error(f"Chyba pri generovaní PDF: {str(e)}")
            raise e
        
        finally:
            if 'session' in locals():
                session.close()

if __name__ == "__main__":
    try:
        setup_logging()
        
        print("=== Optimalizátor rezania a kalkulátor cien skla ===")
        print("Inicializujem systém...")
        
        # Vymazanie existujúcej databázy
        if os.path.exists(DB_PATH):
            try:
                os.remove(DB_PATH)
                print(f"Existujúca databáza bola vymazaná: {DB_PATH}")
            except Exception as e:
                print(f"Nepodarilo sa vymazať databázu: {str(e)}")
        
        # Vytvorenie nových tabuliek
        Base.metadata.create_all(engine)
        print("Nové tabuľky boli vytvorené")
        
        # Inicializácia databázy s kompletnými dátami
        session = Session()
        if not session.query(GlassCategory).first():
            # Vytvorenie všetkých kategórií
            categories = {
                "FLOAT": GlassCategory(name="FLOAT"),
                "PLANIBEL": GlassCategory(name="PLANIBEL"),
                "STOPSOL": GlassCategory(name="STOPSOL"),
                "DRÁTENÉ SKLO": GlassCategory(name="DRÁTENÉ SKLO"),
                "ORNAMENT ČÍRY": GlassCategory(name="ORNAMENT ČÍRY"),
                "ORNAMENT ŽLTÝ": GlassCategory(name="ORNAMENT ŽLTÝ"),
                "CONNEX": GlassCategory(name="CONNEX (STRATOBEL, LEPENÉ)"),
                "LACOBEL": GlassCategory(name="LACOBEL"),
                "MATELAC": GlassCategory(name="MATELAC"),
                "MATELUX": GlassCategory(name="MATELUX - SATINO"),
                "LACOMAT": GlassCategory(name="LACOMAT"),
                "ZRKADLÁ": GlassCategory(name="ZRKADLÁ ČÍRE"),
                "ZRKADLÁ FAREBNÉ": GlassCategory(name="ZRKADLÁ FAREBNÉ")
            }
            
            # Pridanie kategórií do session
            for category in categories.values():
                session.add(category)
            
            # Vytvorenie kompletného zoznamu typov skla
            glasses = [
                # FLOAT
                Glass(name="2 mm antireflexné", category=categories["FLOAT"], price_per_m2=12.21, cutting_fee=5.0, min_area=0.1),
                Glass(name="2 mm Float", category=categories["FLOAT"], price_per_m2=11.67, cutting_fee=5.0, min_area=0.1),
                Glass(name="3 mm Float", category=categories["FLOAT"], price_per_m2=6.41, cutting_fee=5.0, min_area=0.1),
                Glass(name="4mm OPTIWHITE", category=categories["FLOAT"], price_per_m2=12.61, cutting_fee=5.0, min_area=0.1),
                Glass(name="4 mm Float", category=categories["FLOAT"], price_per_m2=7.74, cutting_fee=5.0, min_area=0.1),
                Glass(name="5 mm Float", category=categories["FLOAT"], price_per_m2=9.95, cutting_fee=5.0, min_area=0.1),
                Glass(name="6 mm Float", category=categories["FLOAT"], price_per_m2=12.50, cutting_fee=5.0, min_area=0.1),
                Glass(name="6mm OPTIWHITE", category=categories["FLOAT"], price_per_m2=16.20, cutting_fee=5.0, min_area=0.1),
                Glass(name="8 mm Float", category=categories["FLOAT"], price_per_m2=16.56, cutting_fee=5.0, min_area=0.1),
                Glass(name="8 mm OPTIWHITE", category=categories["FLOAT"], price_per_m2=29.94, cutting_fee=5.0, min_area=0.1),
                Glass(name="10 mm Float", category=categories["FLOAT"], price_per_m2=25.52, cutting_fee=5.0, min_area=0.1),
                Glass(name="10 mm OPTIWHITE", category=categories["FLOAT"], price_per_m2=39.85, cutting_fee=5.0, min_area=0.1),
                Glass(name="12 mm Float", category=categories["FLOAT"], price_per_m2=50.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="Keramické-krbov sklo", category=categories["FLOAT"], price_per_m2=212.50, cutting_fee=5.0, min_area=0.1),

                # PLANIBEL
                Glass(name="3 mm Planibel bronz", category=categories["PLANIBEL"], price_per_m2=8.25, cutting_fee=5.0, min_area=0.1),
                Glass(name="4 mm Planibel bronz + šedý", category=categories["PLANIBEL"], price_per_m2=15.20, cutting_fee=5.0, min_area=0.1),
                Glass(name="5 mm Planibel bronz", category=categories["PLANIBEL"], price_per_m2=16.66, cutting_fee=5.0, min_area=0.1),
                Glass(name="6 mm Planibel bronz + šedý", category=categories["PLANIBEL"], price_per_m2=23.20, cutting_fee=5.0, min_area=0.1),
                Glass(name="6 mm Planibel modrý (dark blue)", category=categories["PLANIBEL"], price_per_m2=23.20, cutting_fee=5.0, min_area=0.1),
                Glass(name="6 mm Planibel zelený", category=categories["PLANIBEL"], price_per_m2=23.20, cutting_fee=5.0, min_area=0.1),
                Glass(name="8 mm Planibel bronz + šedý", category=categories["PLANIBEL"], price_per_m2=38.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="8mm dark grey", category=categories["PLANIBEL"], price_per_m2=50.00, cutting_fee=5.0, min_area=0.1),

                # STOPSOL
                Glass(name="6mm Stopsol bronzový", category=categories["STOPSOL"], price_per_m2=32.65, cutting_fee=5.0, min_area=0.1),

                # DRÁTENÉ SKLO
                Glass(name="6 mm Drátené sklo", category=categories["DRÁTENÉ SKLO"], price_per_m2=24.05, cutting_fee=5.0, min_area=0.1),
                Glass(name="6 mm Pilkington - protipožiarne", category=categories["DRÁTENÉ SKLO"], price_per_m2=70.00, cutting_fee=5.0, min_area=0.1),

                # ORNAMENT ČÍRY
                Glass(name="Konfeta", category=categories["ORNAMENT ČÍRY"], price_per_m2=15.20, cutting_fee=5.0, min_area=0.1),
                Glass(name="Dub biely", category=categories["ORNAMENT ČÍRY"], price_per_m2=15.20, cutting_fee=5.0, min_area=0.1),
                Glass(name="Crepi", category=categories["ORNAMENT ČÍRY"], price_per_m2=15.20, cutting_fee=5.0, min_area=0.1),
                Glass(name="Travertino", category=categories["ORNAMENT ČÍRY"], price_per_m2=6.60, cutting_fee=5.0, min_area=0.1),
                Glass(name="Činčila číra", category=categories["ORNAMENT ČÍRY"], price_per_m2=10.03, cutting_fee=5.0, min_area=0.1),
                Glass(name="Krizet", category=categories["ORNAMENT ČÍRY"], price_per_m2=15.80, cutting_fee=5.0, min_area=0.1),
                Glass(name="Flutes", category=categories["ORNAMENT ČÍRY"], price_per_m2=17.47, cutting_fee=5.0, min_area=0.1),
                Glass(name="Turecký ornament - Turkis, Rose", category=categories["ORNAMENT ČÍRY"], price_per_m2=10.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="Harmony, Boncuk, Kilim, Midye", category=categories["ORNAMENT ČÍRY"], price_per_m2=10.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="Buket, Line", category=categories["ORNAMENT ČÍRY"], price_per_m2=8.33, cutting_fee=5.0, min_area=0.1),
                Glass(name="mastercare- Dominos", category=categories["ORNAMENT ČÍRY"], price_per_m2=25.20, cutting_fee=5.0, min_area=0.1),

                # ORNAMENT ŽLTÝ
                Glass(name="Twist žltý", category=categories["ORNAMENT ŽLTÝ"], price_per_m2=6.08, cutting_fee=5.0, min_area=0.1),

                # CONNEX
                Glass(name="33.1 číre", category=categories["CONNEX"], price_per_m2=19.35, cutting_fee=10.0, min_area=0.1),
                Glass(name="44.1 číre", category=categories["CONNEX"], price_per_m2=23.32, cutting_fee=10.0, min_area=0.1),
                Glass(name="55.1 číre", category=categories["CONNEX"], price_per_m2=28.27, cutting_fee=10.0, min_area=0.1),
                Glass(name="66.1 číre", category=categories["CONNEX"], price_per_m2=31.54, cutting_fee=10.0, min_area=0.1),
                Glass(name="33.1 matované", category=categories["CONNEX"], price_per_m2=35.02, cutting_fee=10.0, min_area=0.1),
                Glass(name="44.1 matované", category=categories["CONNEX"], price_per_m2=31.31, cutting_fee=10.0, min_area=0.1),
                Glass(name="55.1 matované", category=categories["CONNEX"], price_per_m2=35.82, cutting_fee=10.0, min_area=0.1),
                Glass(name="66.1 matované", category=categories["CONNEX"], price_per_m2=38.35, cutting_fee=10.0, min_area=0.1),

                # LACOBEL 4mm
                Glass(name="1014 béžový klasik", category=categories["LACOBEL"], price_per_m2=12.29, cutting_fee=5.0, min_area=0.1),
                Glass(name="3004 burgundy", category=categories["LACOBEL"], price_per_m2=16.32, cutting_fee=5.0, min_area=0.1),
                Glass(name="2001 oranžový klasik", category=categories["LACOBEL"], price_per_m2=14.88, cutting_fee=5.0, min_area=0.1),
                Glass(name="4006 fuchsia", category=categories["LACOBEL"], price_per_m2=12.78, cutting_fee=5.0, min_area=0.1),
                Glass(name="0327 zlatá", category=categories["LACOBEL"], price_per_m2=20.76, cutting_fee=5.0, min_area=0.1),
                Glass(name="8017 tmavohnedý", category=categories["LACOBEL"], price_per_m2=12.78, cutting_fee=5.0, min_area=0.1),
                Glass(name="1023 ostro žltá", category=categories["LACOBEL"], price_per_m2=16.80, cutting_fee=5.0, min_area=0.1),
                Glass(name="9010 krémovo-biely", category=categories["LACOBEL"], price_per_m2=17.37, cutting_fee=5.0, min_area=0.1),
                Glass(name="9005 čierny", category=categories["LACOBEL"], price_per_m2=19.64, cutting_fee=5.0, min_area=0.1),
                Glass(name="1586 červený", category=categories["LACOBEL"], price_per_m2=11.95, cutting_fee=5.0, min_area=0.1),
                Glass(name="1015 bledobéžový", category=categories["LACOBEL"], price_per_m2=18.89, cutting_fee=5.0, min_area=0.1),
                Glass(name="1236 bledohnedý", category=categories["LACOBEL"], price_per_m2=21.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="7035 šedá", category=categories["LACOBEL"], price_per_m2=13.23, cutting_fee=5.0, min_area=0.1),
                Glass(name="7000 modrošedý", category=categories["LACOBEL"], price_per_m2=26.01, cutting_fee=5.0, min_area=0.1),
                Glass(name="0627 tupe metal", category=categories["LACOBEL"], price_per_m2=27.68, cutting_fee=5.0, min_area=0.1),
                Glass(name="9003 čistobiely", category=categories["LACOBEL"], price_per_m2=25.33, cutting_fee=5.0, min_area=0.1),
                Glass(name="1435 modrošedý", category=categories["LACOBEL"], price_per_m2=21.68, cutting_fee=5.0, min_area=0.1),
                Glass(name="9006 šedá metalíza", category=categories["LACOBEL"], price_per_m2=30.94, cutting_fee=5.0, min_area=0.1),
                Glass(name="1013 pearl", category=categories["LACOBEL"], price_per_m2=26.20, cutting_fee=5.0, min_area=0.1),
                Glass(name="0337 starlight black", category=categories["LACOBEL"], price_per_m2=27.12, cutting_fee=5.0, min_area=0.1),
                Glass(name="9007 aluminium", category=categories["LACOBEL"], price_per_m2=20.03, cutting_fee=5.0, min_area=0.1),
                Glass(name="1202 fialový", category=categories["LACOBEL"], price_per_m2=24.68, cutting_fee=5.0, min_area=0.1),

                # LACOBEL 6mm
                Glass(name="9010 krémovo biely 6mm", category=categories["LACOBEL"], price_per_m2=18.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="1013 pearl 6mm", category=categories["LACOBEL"], price_per_m2=37.42, cutting_fee=5.0, min_area=0.1),
                Glass(name="9003 čisto biely 6mm", category=categories["LACOBEL"], price_per_m2=38.68, cutting_fee=5.0, min_area=0.1),
                Glass(name="9005 čierny 6mm", category=categories["LACOBEL"], price_per_m2=24.67, cutting_fee=5.0, min_area=0.1),

                # MATELAC
                Glass(name="2001 oranžový", category=categories["MATELAC"], price_per_m2=31.65, cutting_fee=5.0, min_area=0.1),
                Glass(name="9003 čistobiely", category=categories["MATELAC"], price_per_m2=35.21, cutting_fee=5.0, min_area=0.1),
                Glass(name="1236 bled.hned", category=categories["MATELAC"], price_per_m2=33.90, cutting_fee=5.0, min_area=0.1),
                Glass(name="9005 čierny", category=categories["MATELAC"], price_per_m2=21.85, cutting_fee=5.0, min_area=0.1),
                Glass(name="1013 pearl", category=categories["MATELAC"], price_per_m2=37.16, cutting_fee=5.0, min_area=0.1),
                Glass(name="1015 bled.hned", category=categories["MATELAC"], price_per_m2=29.60, cutting_fee=5.0, min_area=0.1),
                Glass(name="0627 tupe metal", category=categories["MATELAC"], price_per_m2=34.27, cutting_fee=5.0, min_area=0.1),
                Glass(name="silver clear", category=categories["MATELAC"], price_per_m2=50.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="silver grey", category=categories["MATELAC"], price_per_m2=50.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="7035 gray class", category=categories["MATELAC"], price_per_m2=23.21, cutting_fee=5.0, min_area=0.1),
                Glass(name="9006 šedý", category=categories["MATELAC"], price_per_m2=39.24, cutting_fee=5.0, min_area=0.1),
                Glass(name="9010 krem.biel", category=categories["MATELAC"], price_per_m2=21.49, cutting_fee=5.0, min_area=0.1),

                # MATELUX
                Glass(name="číro číre 10mm", category=categories["MATELUX"], price_per_m2=79.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="číro číre 8mm", category=categories["MATELUX"], price_per_m2=46.36, cutting_fee=5.0, min_area=0.1),
                Glass(name="zelený 6mm", category=categories["MATELUX"], price_per_m2=37.72, cutting_fee=5.0, min_area=0.1),
                Glass(name="zelený 8mm", category=categories["MATELUX"], price_per_m2=37.72, cutting_fee=5.0, min_area=0.1),
                Glass(name="bronz 8mm", category=categories["MATELUX"], price_per_m2=45.34, cutting_fee=5.0, min_area=0.1),
                Glass(name="bronz 10mm", category=categories["MATELUX"], price_per_m2=57.44, cutting_fee=5.0, min_area=0.1),
                Glass(name="matované 4mm", category=categories["MATELUX"], price_per_m2=19.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="matované 6mm", category=categories["MATELUX"], price_per_m2=20.24, cutting_fee=5.0, min_area=0.1),
                Glass(name="matované 8mm", category=categories["MATELUX"], price_per_m2=31.42, cutting_fee=5.0, min_area=0.1),
                Glass(name="matované 10mm", category=categories["MATELUX"], price_per_m2=33.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="šedé 8mm", category=categories["MATELUX"], price_per_m2=48.61, cutting_fee=5.0, min_area=0.1),
                Glass(name="dark grey 8mm", category=categories["MATELUX"], price_per_m2=65.55, cutting_fee=5.0, min_area=0.1),
                Glass(name="šedý 10mm", category=categories["MATELUX"], price_per_m2=47.00, cutting_fee=5.0, min_area=0.1),

                # LACOMAT
                Glass(name="matovaný a klasik 4mm", category=categories["LACOMAT"], price_per_m2=18.40, cutting_fee=5.0, min_area=0.1),
                Glass(name="matovaný 5mm", category=categories["LACOMAT"], price_per_m2=20.10, cutting_fee=5.0, min_area=0.1),

                # ZRKADLÁ ČÍRE
                Glass(name="3mm", category=categories["ZRKADLÁ"], price_per_m2=10.23, cutting_fee=5.0, min_area=0.1),
                Glass(name="4mm", category=categories["ZRKADLÁ"], price_per_m2=14.50, cutting_fee=5.0, min_area=0.1),
                Glass(name="5mm", category=categories["ZRKADLÁ"], price_per_m2=18.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="6mm", category=categories["ZRKADLÁ"], price_per_m2=19.00, cutting_fee=5.0, min_area=0.1),

                # ZRKADLÁ FAREBNÉ
                Glass(name="bronzové 4mm", category=categories["ZRKADLÁ FAREBNÉ"], price_per_m2=21.58, cutting_fee=5.0, min_area=0.1),
                Glass(name="šedé 4mm", category=categories["ZRKADLÁ FAREBNÉ"], price_per_m2=21.58, cutting_fee=5.0, min_area=0.1),
                Glass(name="zelené 4mm", category=categories["ZRKADLÁ FAREBNÉ"], price_per_m2=15.00, cutting_fee=5.0, min_area=0.1),
                Glass(name="modré 4mm", category=categories["ZRKADLÁ FAREBNÉ"], price_per_m2=27.76, cutting_fee=5.0, min_area=0.1),
            ]
            
            # Pridanie všetkých typov skla do session
            session.add_all(glasses)
            
            try:
                session.commit()
                print("Databáza bola úspešne inicializovaná s kompletnými dátami")
            except Exception as e:
                session.rollback()
                print(f"Chyba pri inicializácii databázy: {str(e)}")
            finally:
                session.close()
        
        cutting_bot = GlassCuttingBot(TOKEN)
        
        print("\nBot je úspešne spustený a čaká na správy!")
        print("Pre ukončenie stlačte Ctrl+C\n")
        
        cutting_bot.run()
    except KeyboardInterrupt:
        print("\nUkončujem bota...")
    except Exception as e:
        logging.critical(f"Kritická chyba: {str(e)}", exc_info=True)
        print(f"\nNastala chyba: {str(e)}")
    finally:
        print("\nProgram ukončený.")
