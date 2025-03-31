import os
from flask import Flask, render_template, request, jsonify, send_file
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dataclasses import dataclass
import math
import io
from datetime import datetime
import re
import logging
import sys
import time
from decimal import Decimal
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from typing import List, Tuple, Dict

# Konfigurácia
STOCK_WIDTH = 321
STOCK_HEIGHT = 225

# Nastavenie cesty k databáze
DB_PATH = 'glass_calculator.db'

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
        self.user_states = user_states if user_states else {}

    def get_glass_price(self, glass_id: int, width: float, height: float, user_id: int) -> Dict:
        glass = self.session.query(Glass).get(glass_id)
        area = (width * height) / 1000000  # Convert to m²
        
        # Získanie odpadu z user_states pre konkrétneho užívateľa
        waste_percentage = self.user_states.get(user_id, {}).get('total_waste', 0) / 100
            
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
            'waste_price': round(waste_price, 2),
            'total_price': round(base_price + waste_price, 2)
        }

class CuttingOptimizer:
    def __init__(self, stock_width: float, stock_height: float):
        self.stock_width = stock_width
        self.stock_height = stock_height
        self.min_gap = 0.2

    def optimize_multiple_sheets(self, panels: List[GlassPanel]) -> List[Tuple[List[Tuple[float, float, float, float, bool]], float]]:
        remaining_panels = panels.copy()
        all_layouts = []
        sheet_number = 1
        
        while remaining_panels:
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
                    break
            else:
                all_layouts.append((layout, waste))
                break
        
        return all_layouts

    def optimize(self, panels: List[GlassPanel]) -> Tuple[List[Tuple[float, float, float, float, bool]], float]:
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
        
        colors = ['#3498db', '#2ecc71', '#e74c3c', '#f39c12', '#9b59b6', '#1abc9c', '#34495e', '#d35400']
        for i, (x, y, w, h, rotated) in enumerate(layout):
            color = colors[i % len(colors)]
            ax.add_patch(plt.Rectangle((x, y), w, h, fill=True, color=color, alpha=0.7))
            ax.text(x + w/2, y + h/2, 
                   f'{w:.1f}x{h:.1f}\n{"(R)" if rotated else ""}',
                   horizontalalignment='center',
                   verticalalignment='center',
                   fontsize=8,
                   color='white',
                   fontweight='bold')
        
        ax.set_xlim(-10, self.stock_width + 10)
        ax.set_ylim(-10, self.stock_height + 10)
        ax.set_aspect('equal')
        plt.title(f'Optimalizované rozloženie panelov\n{datetime.now().strftime("%Y-%m-%d %H:%M")}')
        plt.grid(True, linestyle='--', alpha=0.7)
        
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
                
                if x < x2 + w2 and x + w > x2 and y < y2 + h2 and y + h > y2:
                    return True
        
        return False

    def generate_pdf(self, layouts: List[Tuple[List[Tuple[float, float, float, float, bool]], float]], glass_name: str, price_info: dict) -> io.BytesIO:
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        # Hlavička
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, "Kalkulácia skla")
        
        # Informácie o skle
        c.setFont("Helvetica", 12)
        y = height - 100
        c.drawString(50, y, f"Typ skla: {glass_name}")
        y -= 20
        c.drawString(50, y, f"Plocha skiel: {price_info['area']:.2f} m² = {price_info['area_price']}€")
        y -= 20
        c.drawString(50, y, f"Plocha odpadu: {price_info['waste_area']:.2f} m² = {price_info['waste_price']}€")
        y -= 20
        c.drawString(50, y, f"Celková cena: {price_info['total_price']}€")
        
        # Pridanie výkresu
        y -= 50
        for i, (layout, waste) in enumerate(layouts):
            img_buf = self.visualize(layout)
            img_reader = ImageReader(img_buf)
            c.drawImage(img_reader, 50, y - 300, width=400, height=300)
            c.drawString(50, y - 320, f"Tabuľa #{i+1} - Odpad: {waste:.1f}%")
            y -= 350
            
            if y < 100 and i < len(layouts) - 1:
                c.showPage()
                y = height - 50
        
        c.save()
        buffer.seek(0)
        return buffer

def parse_dimensions(text: str) -> List[Tuple[float, float]]:
    dimensions = []
    text = text.replace(',', '.').replace(' ', '')
    parts = text.split('-')
    
    for part in parts:
        match = re.match(r'(\d+\.?\d*)x(\d+\.?\d*)', part.lower())
        if match:
            width, height = map(float, match.groups())
            dimensions.append((width, height))

    return dimensions

def validate_dimensions(width: float, height: float, stock_width: float, stock_height: float) -> bool:
    if width <= 0 or height <= 0:
        return False
    
    valid = (width <= stock_width and height <= stock_height) or \
            (height <= stock_width and width <= stock_height)
    
    return valid

def init_db():
    Base.metadata.create_all(engine)
    session = Session()
    
    # Kontrola či už máme kategórie v databáze
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
            # ... ďalšie typy skla z pôvodného kódu
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

# Inicializácia aplikácie
app = Flask(__name__)
user_states = {}

# Inicializácia databázy
init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/categories')
def get_categories():
    session = Session()
    try:
        categories = session.query(GlassCategory).all()
        result = [{'id': cat.id, 'name': cat.name} for cat in categories]
        return jsonify(result)
    finally:
        session.close()

@app.route('/api/glasses/<int:category_id>')
def get_glasses(category_id):
    session = Session()
    try:
        glasses = session.query(Glass).filter_by(category_id=category_id).all()
        result = [{'id': glass.id, 'name': glass.name, 'price': glass.price_per_m2} for glass in glasses]
        return jsonify(result)
    finally:
        session.close()

@app.route('/api/optimize', methods=['POST'])
def optimize():
    data = request.json
    user_id = data.get('user_id', 1)  # Default user_id
    dimensions_text = data.get('dimensions', '')
    stock_width = data.get('stock_width', STOCK_WIDTH)
    stock_height = data.get('stock_height', STOCK_HEIGHT)
    
    dimensions = parse_dimensions(dimensions_text)
    if not dimensions:
        return jsonify({'error': 'Neplatný formát rozmerov'}), 400
    
    panels = []
    for width, height in dimensions:
        if validate_dimensions(width, height, stock_width, stock_height):
            panels.append(GlassPanel(width, height, 4.0))
    
    if not panels:
        return jsonify({'error': 'Žiadne platné rozmery'}), 400
    
    optimizer = CuttingOptimizer(stock_width, stock_height)
    all_layouts = optimizer.optimize_multiple_sheets(panels)
    
    if not all_layouts:
        return jsonify({'error': 'Nepodarilo sa nájsť vhodné rozloženie'}), 400
    
    # Výpočet waste a návrat výsledkov
    result = {
        'layouts': [],
        'total_area': sum(panel.width * panel.height / 10000 for panel in panels),
        'total_waste': 0
    }
    
    for sheet_index, (layout, waste) in enumerate(all_layouts, 1):
        sheet_area = sum(width * height / 10000 for _, _, width, height, _ in layout)
        waste_area = optimizer.calculate_waste_area(sheet_area)
        
        # Vytvoriť base64 obrázok pre tento layout
        img_buf = optimizer.visualize(layout)
        import base64
        img_base64 = base64.b64encode(img_buf.getvalue()).decode('utf-8')
        
        layout_data = {
            'sheet_number': sheet_index,
            'area': round(sheet_area, 2),
            'waste_area': round(waste_area, 2),
            'waste_percentage': round(waste, 1),
            'image': img_base64
        }
        
        result['layouts'].append(layout_data)
        result['total_waste'] += waste
    
    if len(all_layouts) > 0:
        result['average_waste'] = round(result['total_waste'] / len(all_layouts), 1)
    else:
        result['average_waste'] = 0
    
    # Uloženie výsledkov pre neskoršie použitie
    user_states[user_id] = {
        'layouts': all_layouts,
        'total_area': result['total_area'],
        'panels': panels,
        'total_waste': result['total_waste'],
        'stock_width': stock_width,
        'stock_height': stock_height
    }
    
    return jsonify(result)

@app.route('/api/calculate-price', methods=['POST'])
def calculate_price():
    data = request.json
    user_id = data.get('user_id', 1)
    glass_id = data.get('glass_id')
    
    if glass_id is None:
        return jsonify({'error': 'Typ skla nie je uvedený'}), 400
    
    if user_id not in user_states:
        return jsonify({'error': 'Najprv musíte vypočítať rozloženie'}), 400
    
    session = Session()
    try:
        calculator = GlassCalculator(session, user_states)
        total_area = user_states[user_id]['total_area']
        
        price_calculation = calculator.get_glass_price(glass_id, total_area * 1000, 1000, user_id)
        
        # Uložiť výpočet do histórie
        glass = session.query(Glass).get(glass_id)
        calculation = Calculation(
            user_id=user_id,
            glass_id=glass_id,
            width=user_states[user_id]['stock_width'],
            height=user_states[user_id]['stock_height'],
            area=price_calculation['area'],
            waste_area=price_calculation['waste_area'],
            total_price=price_calculation['area_price'] + price_calculation['waste_price']
        )
        session.add(calculation)
        session.commit()
        
        return jsonify(price_calculation)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/generate-pdf', methods=['POST'])
def generate_pdf():
    data = request.json
    user_id = data.get('user_id', 1)
    glass_id = data.get('glass_id')
    
    if glass_id is None:
        return jsonify({'error': 'Typ skla nie je uvedený'}), 400
    
    if user_id not in user_states:
        return jsonify({'error': 'Najprv musíte vypočítať rozloženie'}), 400
    
    session = Session()
    try:
        calculator = GlassCalculator(session, user_states)
        total_area = user_states[user_id]['total_area']
        
        price_calculation = calculator.get_glass_price(glass_id, total_area * 1000, 1000, user_id)
        glass = session.query(Glass).get(glass_id)
        
        optimizer = CuttingOptimizer(
            user_states[user_id]['stock_width'], 
            user_states[user_id]['stock_height']
        )
        
        pdf_buffer = optimizer.generate_pdf(
            user_states[user_id]['layouts'],
            glass.name,
            price_calculation
        )
        
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name='kalkulacia_skla.pdf',
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/history/<int:user_id>')
def get_history(user_id):
    session = Session()
    try:
        calculations = session.query(Calculation).filter_by(user_id=user_id)\
                              .order_by(Calculation.created_at.desc()).limit(10).all()
        
        result = []
        for calc in calculations:
            glass = session.query(Glass).get(calc.glass_id)
            result.append({
                'id': calc.id,
                'date': calc.created_at.strftime('%d.%m.%Y %H:%M'),
                'area': round(calc.area, 2),
                'waste_area': round(calc.waste_area, 2),
                'total_price': round(calc.total_price, 2),
                'glass_name': glass.name
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/clear-history/<int:user_id>', methods=['POST'])
def clear_history(user_id):
    session = Session()
    try:
        session.query(Calculation).filter_by(user_id=user_id).delete()
        session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

if __name__ == '__main__':
    # Inicializácia databázy
    init_db()
    # V lokálnom prostredí spustíme s debug režimom
    app.run(debug=True)
else:
    # Na Vercel sa automaticky spustí cez WSGI
    # Inicializujeme databázu aj tu
    init_db() 