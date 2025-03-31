// Globálne premenné
let userId = Date.now(); // Jednoduchý spôsob identifikácie používateľa
let selectedStockWidth = 321; // Predvolená šírka
let selectedStockHeight = 225; // Predvolená výška
let dimensions = []; // Zoznam rozmerov skiel
let selectedGlassId = null; // ID vybraného typu skla
let optimizationResults = null; // Výsledky optimalizácie

// Pomocné funkcie
function formatDimensions(width, height) {
    return `${width} × ${height} cm`;
}

function formatNumber(number, decimals = 2) {
    return number.toFixed(decimals).replace('.', ',');
}

function formatPrice(price) {
    return `${formatNumber(price)} €`;
}

function showStep(stepNumber) {
    // Skryť všetky kroky
    document.querySelectorAll('.step-section').forEach(section => {
        section.classList.remove('active');
    });
    
    // Zobraziť vybraný krok
    document.getElementById(`step${stepNumber}`).classList.add('active');
    
    // Aktualizovať kroky v sprievodcovi
    document.querySelectorAll('.step-item').forEach(item => {
        const itemStep = parseInt(item.getAttribute('data-step'));
        item.classList.remove('active', 'completed');
        
        if (itemStep === stepNumber) {
            item.classList.add('active');
        } else if (itemStep < stepNumber) {
            item.classList.add('completed');
        }
    });
}

// Inicializácia pri načítaní stránky
document.addEventListener('DOMContentLoaded', function() {
    // Zobrazenie prvého kroku
    showStep(1);
    
    // Inicializácia modálnych okien
    initializeModals();
    
    // Inicializácia kroku 1 - výber rozmerov tabule
    initStep1();
    
    // Inicializácia kroku 2 - zadanie rozmerov skiel
    initStep2();
    
    // Inicializácia kroku 3 - optimalizácia
    initStep3();
    
    // Inicializácia kroku 4 - výber typu skla
    initStep4();
    
    // Inicializácia kroku 5 - výpočet ceny
    initStep5();
});

// Inicializácia modálnych okien
function initializeModals() {
    // Tlačidlá na otvorenie modálnych okien
    document.getElementById('historyBtn').addEventListener('click', function() {
        openModal('historyModal');
        loadHistory();
    });
    
    document.getElementById('helpBtn').addEventListener('click', function() {
        openModal('helpModal');
    });
    
    // Zatvorenie modálnych okien
    document.querySelectorAll('.close-btn, .close-modal').forEach(btn => {
        btn.addEventListener('click', function() {
            const modal = this.closest('.modal');
            closeModal(modal.id);
        });
    });
    
    // Zatvorenie modálneho okna kliknutím mimo obsahu
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function(event) {
            if (event.target === this) {
                closeModal(this.id);
            }
        });
    });
    
    // Vymazanie histórie
    document.getElementById('clearHistoryBtn').addEventListener('click', function() {
        clearHistory();
    });
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.add('active');
    document.body.style.overflow = 'hidden'; // Zabrániť scrollovaniu na pozadí
    
    // Animovať modalIn
    const modalContent = modal.querySelector('.modal-content');
    modalContent.style.animation = 'none';
    setTimeout(() => {
        modalContent.style.animation = 'modalIn var(--transition-medium)';
    }, 10);
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.remove('active');
    document.body.style.overflow = ''; // Obnoviť scrollovanie
}

// Inicializácia kroku 1 - výber rozmerov tabule
function initStep1() {
    // Výber karty s rozmermi
    const dimensionCards = document.querySelectorAll('.dimension-card');
    dimensionCards.forEach(card => {
        card.addEventListener('click', function() {
            // Odstrániť označenie zo všetkých kariet
            dimensionCards.forEach(c => c.classList.remove('selected'));
            
            // Označiť vybranú kartu
            this.classList.add('selected');
            
            // Získať rozmery
            if (this.classList.contains('custom')) {
                // Pri vlastnej veľkosti získať hodnoty z inputov
                const customWidth = parseFloat(document.getElementById('customWidth').value);
                const customHeight = parseFloat(document.getElementById('customHeight').value);
                
                if (customWidth && customHeight) {
                    selectedStockWidth = customWidth;
                    selectedStockHeight = customHeight;
                }
            } else {
                // Pri predvolených rozmeroch získať hodnoty z data atribútov
                selectedStockWidth = parseFloat(this.getAttribute('data-width'));
                selectedStockHeight = parseFloat(this.getAttribute('data-height'));
            }
        });
    });
    
    // Custom rozmery - aktualizovať hodnoty po zmene
    document.getElementById('customWidth').addEventListener('input', function() {
        const customCard = document.querySelector('.dimension-card.custom');
        customCard.classList.add('selected');
        dimensionCards.forEach(c => {
            if (!c.classList.contains('custom')) {
                c.classList.remove('selected');
            }
        });
        
        selectedStockWidth = parseFloat(this.value) || 0;
    });
    
    document.getElementById('customHeight').addEventListener('input', function() {
        const customCard = document.querySelector('.dimension-card.custom');
        customCard.classList.add('selected');
        dimensionCards.forEach(c => {
            if (!c.classList.contains('custom')) {
                c.classList.remove('selected');
            }
        });
        
        selectedStockHeight = parseFloat(this.value) || 0;
    });
    
    // Tlačidlo Pokračovať
    document.getElementById('nextToStep2').addEventListener('click', function() {
        // Overiť, či je vybraná karta
        if (selectedStockWidth <= 0 || selectedStockHeight <= 0) {
            alert('Prosím, vyberte alebo zadajte platné rozmery tabule.');
            return;
        }
        
        showStep(2);
    });
}

// Inicializácia kroku 2 - zadanie rozmerov skiel
function initStep2() {
    // Spracovanie vstupu rozmerov
    document.getElementById('dimensions').addEventListener('input', function() {
        const text = this.value;
        const lines = text.split(/[\n-]/);
        
        dimensions = [];
        
        lines.forEach(line => {
            // Odstrániť biele znaky a nahradiť medzery
            const sanitized = line.trim().replace(/\s+/g, '');
            
            // Kontrola formátu ŠxV (napr. 100x50)
            const match = sanitized.match(/^(\d+[.,]?\d*)x(\d+[.,]?\d*)$/i);
            if (match) {
                const width = parseFloat(match[1].replace(',', '.'));
                const height = parseFloat(match[2].replace(',', '.'));
                
                // Pridať rozmer, ak je platný
                if (width > 0 && height > 0) {
                    dimensions.push({ width, height });
                }
            }
        });
        
        updateDimensionsList();
    });
    
    // Vymazanie všetkých rozmerov
    document.getElementById('clearDimensions').addEventListener('click', function() {
        document.getElementById('dimensions').value = '';
        dimensions = [];
        updateDimensionsList();
    });
    
    // Tlačidlo Späť
    document.getElementById('backToStep1').addEventListener('click', function() {
        showStep(1);
    });
    
    // Tlačidlo Vypočítať
    document.getElementById('nextToStep3').addEventListener('click', function() {
        // Overiť, či sú zadané rozmery
        if (dimensions.length === 0) {
            alert('Prosím, zadajte aspoň jeden rozmer skla.');
            return;
        }
        
        // Prejsť na ďalší krok a spustiť optimalizáciu
        showStep(3);
        runOptimization();
    });
}

// Aktualizácia zoznamu rozmerov
function updateDimensionsList() {
    const list = document.getElementById('dimensionList');
    list.innerHTML = '';
    
    dimensions.forEach((dim, index) => {
        const li = document.createElement('li');
        li.innerHTML = `
            <span class="dimension-value">${dim.width} × ${dim.height} cm</span>
            <div class="dimension-actions">
                <button class="btn-icon" data-index="${index}">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        
        list.appendChild(li);
        
        // Pridať event listener na tlačidlo odstránenia
        li.querySelector('.btn-icon').addEventListener('click', function() {
            const index = parseInt(this.getAttribute('data-index'));
            dimensions.splice(index, 1);
            updateDimensionsList();
        });
    });
}

// Inicializácia kroku 3 - optimalizácia
function initStep3() {
    // Tlačidlo Späť
    document.getElementById('backToStep2').addEventListener('click', function() {
        showStep(2);
    });
    
    // Tlačidlo Pokračovať
    document.getElementById('nextToStep4').addEventListener('click', function() {
        if (!optimizationResults) {
            alert('Prosím, počkajte na dokončenie výpočtu.');
            return;
        }
        
        showStep(4);
        loadGlassCategories();
    });
}

// Spustenie optimalizácie
function runOptimization() {
    // Zobraziť loading
    document.getElementById('optimizationLoading').style.display = 'flex';
    document.getElementById('optimizationResults').classList.add('hide');
    
    // Pripraviť dáta pre API
    const dimensionsText = dimensions.map(dim => `${dim.width}x${dim.height}`).join('-');
    const data = {
        user_id: userId,
        dimensions: dimensionsText,
        stock_width: selectedStockWidth,
        stock_height: selectedStockHeight
    };
    
    // Odoslať požiadavku na API
    fetch('/api/optimize', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errorData => {
                throw new Error(errorData.error || 'Nastala chyba pri optimalizácii');
            });
        }
        return response.json();
    })
    .then(data => {
        // Uložiť výsledky
        optimizationResults = data;
        
        // Aktualizovať rozhranie
        displayOptimizationResults(data);
    })
    .catch(error => {
        alert(error.message);
        console.error('Chyba optimalizácie:', error);
        
        // Vrátiť sa na predchádzajúci krok
        showStep(2);
    })
    .finally(() => {
        // Skryť loading
        document.getElementById('optimizationLoading').style.display = 'none';
    });
}

// Zobrazenie výsledkov optimalizácie
function displayOptimizationResults(data) {
    // Zobraziť výsledky
    document.getElementById('optimizationResults').classList.remove('hide');
    
    // Aktualizovať súhrn
    document.getElementById('sheetsCount').textContent = data.layouts.length;
    document.getElementById('totalArea').textContent = `${formatNumber(data.total_area)} m²`;
    document.getElementById('averageWaste').textContent = `${formatNumber(data.average_waste)}%`;
    
    // Vyprázdniť a naplniť container s layoutmi
    const layoutsContainer = document.getElementById('layoutsContainer');
    layoutsContainer.innerHTML = '';
    
    // Pridať jednotlivé layouty
    data.layouts.forEach((layout, index) => {
        const layoutCard = document.createElement('div');
        layoutCard.className = 'layout-card';
        
        const utilization = 100 - layout.waste_percentage;
        
        layoutCard.innerHTML = `
            <div class="layout-header">
                <h3 class="layout-title">Tabuľa #${index + 1}</h3>
                <div class="layout-stats">
                    <div class="layout-stat">
                        <i class="fas fa-border-all"></i>
                        <span>${formatNumber(layout.area)} m²</span>
                    </div>
                    <div class="layout-stat">
                        <i class="fas fa-trash-alt"></i>
                        <span>${formatNumber(layout.waste_area)} m²</span>
                    </div>
                    <div class="layout-stat">
                        <i class="fas fa-percentage"></i>
                        <span>Využitie: ${formatNumber(utilization)}%</span>
                    </div>
                </div>
            </div>
            <div class="layout-body">
                <img src="data:image/png;base64,${layout.image}" alt="Layout ${index + 1}" class="layout-image">
            </div>
        `;
        
        layoutsContainer.appendChild(layoutCard);
    });
    
    // Efekt postupného zobrazovania layoutov
    const cards = layoutsContainer.querySelectorAll('.layout-card');
    cards.forEach((card, index) => {
        setTimeout(() => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            card.style.transition = 'all var(--transition-medium)';
            
            setTimeout(() => {
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, 50);
        }, index * 100);
    });
}

// Inicializácia kroku 4 - výber typu skla
function initStep4() {
    // Tlačidlo Späť
    document.getElementById('backToStep3').addEventListener('click', function() {
        showStep(3);
    });
    
    // Tlačidlo Pokračovať
    document.getElementById('nextToStep5').addEventListener('click', function() {
        if (!selectedGlassId) {
            alert('Prosím, vyberte typ skla.');
            return;
        }
        
        showStep(5);
        calculatePrice();
    });
    
    // Zmena kategórie skla
    document.getElementById('glassCategory').addEventListener('change', function() {
        const categoryId = this.value;
        if (categoryId) {
            loadGlassTypes(categoryId);
        } else {
            document.getElementById('glassTypesList').innerHTML = '';
            document.getElementById('nextToStep5').disabled = true;
        }
    });
}

// Načítanie kategórií skla
function loadGlassCategories() {
    fetch('/api/categories')
        .then(response => response.json())
        .then(categories => {
            const select = document.getElementById('glassCategory');
            
            // Vynulovať select
            select.innerHTML = '<option value="">-- Vyberte kategóriu --</option>';
            
            // Pridať kategórie
            categories.forEach(category => {
                const option = document.createElement('option');
                option.value = category.id;
                option.textContent = category.name;
                select.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Chyba pri načítaní kategórií:', error);
            alert('Nepodarilo sa načítať kategórie skla.');
        });
}

// Načítanie typov skla podľa kategórie
function loadGlassTypes(categoryId) {
    fetch(`/api/glasses/${categoryId}`)
        .then(response => response.json())
        .then(glasses => {
            const container = document.getElementById('glassTypesList');
            container.innerHTML = '';
            
            // Pridať typy skla
            glasses.forEach(glass => {
                const card = document.createElement('div');
                card.className = 'glass-type-card';
                card.setAttribute('data-id', glass.id);
                
                card.innerHTML = `
                    <div class="glass-name">${glass.name}</div>
                    <div class="glass-price">${formatPrice(glass.price)} <span>/ m²</span></div>
                    <div class="glass-details">
                        <div class="glass-detail">
                            <span>Hrúbka</span>
                            <span>${glass.name.match(/\d+(\.\d+)?\s*mm/) || ['N/A']}</span>
                        </div>
                    </div>
                `;
                
                // Pridať event listener
                card.addEventListener('click', function() {
                    // Odstrániť označenie zo všetkých kariet
                    document.querySelectorAll('.glass-type-card').forEach(c => c.classList.remove('selected'));
                    
                    // Označiť vybranú kartu
                    this.classList.add('selected');
                    
                    // Uložiť ID vybraného typu skla
                    selectedGlassId = glass.id;
                    
                    // Povoliť tlačidlo Pokračovať
                    document.getElementById('nextToStep5').disabled = false;
                });
                
                container.appendChild(card);
            });
            
            // Efekt postupného zobrazovania kariet
            const cards = container.querySelectorAll('.glass-type-card');
            cards.forEach((card, index) => {
                setTimeout(() => {
                    card.style.opacity = '0';
                    card.style.transform = 'translateY(20px)';
                    card.style.transition = 'all var(--transition-medium)';
                    
                    setTimeout(() => {
                        card.style.opacity = '1';
                        card.style.transform = 'translateY(0)';
                    }, 50);
                }, index * 50);
            });
        })
        .catch(error => {
            console.error('Chyba pri načítaní typov skla:', error);
            alert('Nepodarilo sa načítať typy skla.');
        });
}

// Inicializácia kroku 5 - výpočet ceny
function initStep5() {
    // Tlačidlo generovať PDF
    document.getElementById('generatePdfBtn').addEventListener('click', function() {
        generatePdf();
    });
    
    // Tlačidlo nový výpočet
    document.getElementById('newCalculationBtn').addEventListener('click', function() {
        // Vynulovať vybrané hodnoty
        selectedGlassId = null;
        optimizationResults = null;
        
        // Zobraziť prvý krok
        showStep(1);
    });
}

// Výpočet ceny
function calculatePrice() {
    // Pripraviť dáta pre API
    const data = {
        user_id: userId,
        glass_id: selectedGlassId
    };
    
    // Odoslať požiadavku na API
    fetch('/api/calculate-price', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errorData => {
                throw new Error(errorData.error || 'Nastala chyba pri výpočte ceny');
            });
        }
        return response.json();
    })
    .then(data => {
        // Aktualizovať rozhranie
        displayPriceCalculation(data);
    })
    .catch(error => {
        alert(error.message);
        console.error('Chyba výpočtu ceny:', error);
    });
}

// Zobrazenie výpočtu ceny
function displayPriceCalculation(data) {
    document.getElementById('glassName').textContent = data.glass_name;
    document.getElementById('pricePerM2').textContent = `${formatPrice(data.area_price / data.area)} / m²`;
    document.getElementById('glassArea').textContent = `${formatNumber(data.area)} m²`;
    document.getElementById('areaPrice').textContent = formatPrice(data.area_price);
    document.getElementById('wasteArea').textContent = `${formatNumber(data.waste_area)} m²`;
    document.getElementById('wastePrice').textContent = formatPrice(data.waste_price);
    document.getElementById('totalPrice').textContent = formatPrice(data.total_price);
    
    // Pridať efekt počítania ceny
    animateCountUp('totalPrice', data.total_price);
}

// Animácia počítania ceny
function animateCountUp(elementId, targetValue) {
    const element = document.getElementById(elementId);
    const duration = 1000; // Trvanie animácie v ms
    const startValue = 0;
    const startTime = performance.now();
    
    function updateValue(currentTime) {
        const elapsedTime = currentTime - startTime;
        const progress = Math.min(elapsedTime / duration, 1);
        const easedProgress = progress * (2 - progress); // Easing funkcia
        
        const value = startValue + ((targetValue - startValue) * easedProgress);
        element.textContent = `${formatPrice(value)}`;
        
        if (progress < 1) {
            requestAnimationFrame(updateValue);
        }
    }
    
    requestAnimationFrame(updateValue);
}

// Generovanie PDF
function generatePdf() {
    // Pripraviť dáta pre API
    const data = {
        user_id: userId,
        glass_id: selectedGlassId
    };
    
    // Odoslať požiadavku na API
    fetch('/api/generate-pdf', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errorData => {
                throw new Error(errorData.error || 'Nastala chyba pri generovaní PDF');
            });
        }
        return response.blob();
    })
    .then(blob => {
        // Vytvoriť URL pre stiahnutie
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'kalkulacia_skla.pdf';
        a.click();
        window.URL.revokeObjectURL(url);
    })
    .catch(error => {
        alert(error.message);
        console.error('Chyba generovania PDF:', error);
    });
}

// Načítanie histórie
function loadHistory() {
    fetch(`/api/history/${userId}`)
        .then(response => response.json())
        .then(data => {
            const tableBody = document.getElementById('historyTableBody');
            const emptyHistory = document.getElementById('emptyHistory');
            
            if (data.length === 0) {
                tableBody.innerHTML = '';
                emptyHistory.classList.remove('hide');
                return;
            }
            
            emptyHistory.classList.add('hide');
            tableBody.innerHTML = '';
            
            // Pridať záznamy z histórie
            data.forEach(record => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${record.date}</td>
                    <td>${record.glass_name}</td>
                    <td>${formatNumber(record.area)} m²</td>
                    <td>${formatNumber(record.waste_area)} m²</td>
                    <td>${formatPrice(record.total_price)}</td>
                `;
                tableBody.appendChild(row);
            });
        })
        .catch(error => {
            console.error('Chyba pri načítaní histórie:', error);
            alert('Nepodarilo sa načítať históriu.');
        });
}

// Vymazanie histórie
function clearHistory() {
    if (!confirm('Naozaj chcete vymazať celú históriu kalkulácií?')) {
        return;
    }
    
    fetch(`/api/clear-history/${userId}`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Aktualizovať zobrazenie histórie
            document.getElementById('historyTableBody').innerHTML = '';
            document.getElementById('emptyHistory').classList.remove('hide');
            alert('História bola úspešne vymazaná.');
        } else {
            throw new Error(data.error || 'Nastala chyba pri vymazávaní histórie');
        }
    })
    .catch(error => {
        alert(error.message);
        console.error('Chyba pri vymazávaní histórie:', error);
    });
} 