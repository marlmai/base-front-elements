// Загрузка списка документов
async function loadDocuments() {
    const container = document.getElementById('documentsList');
    const countEl = document.getElementById('documentsCount');
    
    if (!container) return;
    
    try {
        const response = await fetch('/api/documents/');
        const files = await response.json();
        
        if (!files.length) {
            container.innerHTML = '<div class="doc-item" style="justify-content: center; opacity: 0.5;">📭 No documents</div>';
            if (countEl) countEl.textContent = '0';
            return;
        }
        
        // Формируем список с нумерацией
        let html = '';
        files.forEach((file, index) => {
            // Номер с ведущим нулём (01, 02...)
            const number = (index + 1).toString().padStart(2, ' ');
            
            // Имя файла (без расширения, красивое)
            let name = file.name.replace(/\.pdf$/i, '');
            name = name.replace(/[_\-]/g, ' ');
            
            html += `
                <div class="doc-item" onclick="selectDocument('${file.name}')">
                    <div class="doc-number">${number}</div>
                    <div class="doc-icon">📄</div>
                    <div class="doc-name">${escapeHtml(name)}</div>
                </div>
            `;
        });
        
        container.innerHTML = html;
        if (countEl) countEl.textContent = files.length;
        
    } catch (error) {
        console.error('Error loading documents:', error);
        container.innerHTML = '<div class="doc-item" style="justify-content: center; opacity: 0.5;">❌ Error loading</div>';
    }
}

// Функция выбора документа
function selectDocument(fileName) {
    console.log('Selected document:', fileName);
    
    // Убираем активный класс со всех
    document.querySelectorAll('.doc-item').forEach(el => {
        el.classList.remove('active');
    });
    
    // Добавляем активный класс на выбранный
    event?.currentTarget?.classList.add('active');
    
    // Сохраняем выбранный документ
    window.selectedDocument = fileName;
}

// Функция экранирования HTML (безопасность)
function escapeHtml(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// Загружаем документы при старте
document.addEventListener('DOMContentLoaded', loadDocuments);