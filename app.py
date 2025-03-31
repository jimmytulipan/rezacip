import os
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict
from dataclasses import dataclass
import io
from datetime import datetime
import json
import re
import math
import sys
import time
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# Flask aplikácia
app = Flask(__name__)

# Konfigurácia SQLite databázy
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'glass_calculator.db')
Base = declarative_base()
engine = create_engine(f'sqlite:///{DB_PATH}')
Session = sessionmaker(bind=engine)

# Databázové modely
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

# Triedy pre optimalizáciu rezania
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

class CuttingOptimizer:
    def __init__(self, stock_width: float, stock_height: float):
        self.stock_width = stock_width
        self.stock_height = stock_height
        self.min_gap = 0.2
        
    def optimize(self, panels: List[GlassPanel]) -> Tuple[List[Tuple[float, float, float, float, bool]], float]:
        # Zjednodušená optimalizácia pre demo
        layout = []
        x, y = 0, 0
        max_height_in_row = 0
        
        for panel in panels:
            width, height = panel.get_dimensions()
            
            # Ak panel presahuje šírku tabule, prejdi na nový riadok
            if x + width > self.stock_width:
                x = 0
                y += max_height_in_row + self.min_gap
                max_height_in_row = 0
            
            # Ak panel presahuje výšku tabule, koniec
            if y + height > self.stock_height:
                break
                
            layout.append((x, y, width, height, panel.rotated))
            
            # Aktualizácia pozície pre ďalší panel
            x += width + self.min_gap
            max_height_in_row = max(max_height_in_row, height)
        
        # Výpočet odpadu
        used_area = sum(width * height for _, _, width, height, _ in layout)
        total_area = self.stock_width * self.stock_height
        waste = ((total_area - used_area) / total_area) * 100
        
        return layout, waste
    
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
        plt.title(f'Optimalizované rozloženie panelov\n{datetime.now().strftime("%Y-%m-%d %H:%M")}')
        plt.grid(True)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        return buf

class GlassCalculator:
    def __init__(self, session):
        self.session = session

    def get_glass_price(self, glass_id: int, width: float, height: float) -> Dict:
        glass = self.session.query(Glass).get(glass_id)
        area = (width * height) / 1000000  # Convert to m²
        
        # Ensure minimum area
        if area < glass.min_area:
            area = glass.min_area
            
        # Cena za plochu
        base_price = area * glass.price_per_m2
        
        return {
            'glass_name': glass.name,
            'dimensions': f"{width}x{height}mm",
            'area': round(area, 2),
            'area_price': round(base_price, 2)
        }

# Vytvorenie tabuliek v databáze
Base.metadata.create_all(engine)

# Routy aplikácie
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/categories')
def get_categories():
    session = Session()
    try:
        categories = session.query(GlassCategory).all()
        return jsonify([{'id': cat.id, 'name': cat.name} for cat in categories])
    finally:
        session.close()

@app.route('/glasses/<int:category_id>')
def get_glasses(category_id):
    session = Session()
    try:
        glasses = session.query(Glass).filter_by(category_id=category_id).all()
        return jsonify([{
            'id': glass.id, 
            'name': glass.name,
            'price_per_m2': glass.price_per_m2,
            'cutting_fee': glass.cutting_fee,
            'min_area': glass.min_area
        } for glass in glasses])
    finally:
        session.close()

@app.route('/optimize', methods=['POST'])
def optimize_cutting():
    data = request.json
    stock_size = data.get('stock_size', {'width': 321, 'height': 225})
    glass_dimensions = data.get('dimensions', [])
    
    # Vytvorenie optimalizéra a panelov
    optimizer = CuttingOptimizer(stock_size['width'], stock_size['height'])
    panels = [GlassPanel(dim['width'], dim['height'], 4.0) for dim in glass_dimensions]
    
    # Optimalizácia
    layout, waste = optimizer.optimize(panels)
    
    # Vizualizácia
    img_buf = optimizer.visualize(layout)
    img_base64 = img_to_base64(img_buf)
    
    # Výpočet celkovej plochy skiel
    total_area = sum(panel.width * panel.height / 10000 for panel in panels)
    
    return jsonify({
        'layout': [{'x': x, 'y': y, 'width': w, 'height': h, 'rotated': r} for x, y, w, h, r in layout],
        'waste_percentage': round(waste, 2),
        'visualization': img_base64,
        'total_area': round(total_area, 2)
    })

@app.route('/calculate_price', methods=['POST'])
def calculate_price():
    data = request.json
    glass_id = data.get('glass_id')
    area = data.get('area', 0)
    
    session = Session()
    try:
        calculator = GlassCalculator(session)
        price_data = calculator.get_glass_price(glass_id, math.sqrt(area * 1000000), math.sqrt(area * 1000000))
        return jsonify(price_data)
    finally:
        session.close()

# Pomocné funkcie
def img_to_base64(img_buf):
    import base64
    img_buf.seek(0)
    img_base64 = base64.b64encode(img_buf.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{img_base64}"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000))) 