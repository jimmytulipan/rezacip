from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
import os
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
import sys

app = Flask(__name__, 
            template_folder='../templates',
            static_folder='../static')

# Import hlavného app.py pre funkčnosť aplikácie
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import *

# Toto je pre Vercel
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))) 