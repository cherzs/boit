import re

with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update the Modal HTML
new_modal_html = """    <!-- PRODUCT DETAIL MODAL -->
    <div class="modal-overlay" id="modalOverlay" onclick="closeModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <button class="modal-close"
                onclick="document.getElementById('modalOverlay').classList.remove('active')">&times;</button>
            <input type="hidden" id="modalProductUrl">
            <div class="form-group" style="margin-bottom: 1.2rem; margin-top: 1rem;">
                <label>Product Title</label>
                <input type="text" id="modalTitleInput" style="font-weight:700; font-size:1.05rem;" autocomplete="off">
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.8rem; margin-bottom:1rem">
                <div class="modal-field form-group" style="margin-bottom: 0;">
                    <label>Price ($)</label>
                    <input type="number" step="0.01" id="modalPriceInput" style="color:var(--green); font-weight:700; font-size:1.1rem; width:100%;" autocomplete="off">
                </div>
                <div class="modal-field">
                    <div class="label">Item Type</div>
                    <div class="value" id="modalCategory" style="margin-top:0.4rem">-</div>
                </div>"""

content = re.sub(
    r'<!-- PRODUCT DETAIL MODAL -->.*?<div class="modal-field">\s*<div class="label">Item Type</div>\s*<div class="value" id="modalCategory">-</div>\s*</div>',
    new_modal_html,
    content,
    flags=re.DOTALL
)

# 2. Add Save button to Modal Footer
save_btn = """            <a class="modal-link" id="modalLink" href="#" target="_blank">Open on ZeusX &rarr;</a>
            <div style="margin-top: 1.5rem; display: flex; justify-content: flex-end; gap: 0.8rem; border-top: 1px solid var(--border); padding-top: 1rem;">
                <button class="btn btn-outline" style="width:auto; margin:0;" onclick="document.getElementById('modalOverlay').classList.remove('active')">Close</button>
                <button class="btn btn-success" style="width:auto; margin:0;" onclick="saveProductFromModal()">Save Changes</button>
            </div>
        </div>
    </div>"""

content = re.sub(
    r'<a class="modal-link" id="modalLink" href="#" target="_blank">Open on ZeusX &rarr;</a>\s*</div>\s*</div>',
    save_btn,
    content
)

# 3. Update JS showProductDetail logic
new_js_detail = """        async function showProductDetail(encodedUrl) {
            const url = decodeURIComponent(encodedUrl);
            const p = await api(`product/detail?url=${encodeURIComponent(url)}`);
            if (!p) return;

            document.getElementById('modalProductUrl').value = p.url || '';
            document.getElementById('modalTitleInput').value = p.title || '';
            document.getElementById('modalPriceInput').value = p.price || '0';
            document.getElementById('modalQty').textContent = p.quantity || '-';"""

content = re.sub(
    r'async function showProductDetail.*?document\.getElementById\(\'modalQty\'\)\.textContent = p\.quantity \|\| \'-\';',
    new_js_detail,
    content,
    flags=re.DOTALL
)

# 4. Remove inline editing from product list
content = re.sub(
    r'if \(isEditing\) \{.*?\}\s*return `\s*<div class="product-card',
    'return `\n                <div class="product-card',
    content,
    flags=re.DOTALL
)
# And the `isEditing` variable
content = re.sub(
    r'const isEditing = editingProductUrl === p\.url;\n\s*',
    '',
    content
)

# Remove the inline Edit button
content = re.sub(
    r'<button onclick="editProduct\(\'\$\{encodeURIComponent\(p\.url\)\}\'\)" title="Edit">Edit</button>\n\s*',
    '',
    content
)

# 5. Add saveProductFromModal and remove editProduct, saveProductEdit, cancelProductEdit
new_js_save = """        async function saveProductFromModal() {
            const url = document.getElementById('modalProductUrl').value;
            const newTitle = document.getElementById('modalTitleInput').value;
            const newPrice = document.getElementById('modalPriceInput').value;

            if (!url) return;

            await api('product/update', 'POST', {
                url,
                title: newTitle,
                price: parseFloat(newPrice) || 0
            });

            showToast('Product updated!', 'success');
            document.getElementById('modalOverlay').classList.remove('active');
            loadProducts();
        }"""

content = re.sub(
    r'function editProduct.*?\}\s*function cancelProductEdit\(\) \{.*?\}',
    new_js_save,
    content,
    flags=re.DOTALL
)

with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Update successful')
