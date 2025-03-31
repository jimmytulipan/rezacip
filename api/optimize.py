from flask import Flask, request, jsonify
import base64
from io import BytesIO
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sys
import os

# Pridáme cestu k hlavnému adresáru
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

# Importujeme triedy z hlavnej aplikácie
from app import GlassPanel, CuttingOptimizer

app = Flask(__name__)

@app.route('/api/optimize', methods=['POST'])
def optimize():
    try:
        data = request.json
        stock_size = data.get('stock_size', {'width': 321, 'height': 225})
        glass_dimensions = data.get('dimensions', [])
        
        # Vytvorenie optimalizéra a panelov
        optimizer = CuttingOptimizer(stock_size['width'], stock_size['height'])
        panels = [GlassPanel(dim['width'], dim['height'], 4.0) for dim in glass_dimensions]
        
        # Optimalizácia
        layout, waste = optimizer.optimize(panels)
        
        # Vizualizácia - používame priamo matplotlib bez pyplot
        # Tento prístup je odporúčaný pre serverless prostredie
        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(111)
        
        ax.add_patch(plt.Rectangle((0, 0), optimizer.stock_width, optimizer.stock_height, 
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
        
        ax.set_xlim(-10, optimizer.stock_width + 10)
        ax.set_ylim(-10, optimizer.stock_height + 10)
        ax.set_aspect('equal')
        ax.set_title(f'Optimalizované rozloženie panelov')
        ax.grid(True)
        
        # Uloženie do buffera
        buf = BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close(fig)
        
        # Výpočet celkovej plochy skiel
        total_area = sum(panel.width * panel.height / 10000 for panel in panels)
        
        return jsonify({
            'layout': [{'x': x, 'y': y, 'width': w, 'height': h, 'rotated': r} for x, y, w, h, r in layout],
            'waste_percentage': round(waste, 2),
            'visualization': f"data:image/png;base64,{img_base64}",
            'total_area': round(total_area, 2)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return jsonify({"error": "Route not found"}), 404

# Toto je potrebné pre Vercel serverless funkcie
def handler(event, context):
    return app(event, context) 