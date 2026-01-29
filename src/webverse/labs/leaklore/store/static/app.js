const state = {
  products: [],
  cartCount: 0,
  filter: "all",
  query: ""
};

function money(n){
  const v = Number(n || 0);
  return `$${v.toFixed(2)}`;
}

function categorize(p){
  const name = (p.name || "").toLowerCase();
  if (name.includes("hoodie") || name.includes("shirt") || name.includes("apparel")) return "apparel";
  if (name.includes("wallet") || name.includes("edc")) return "edc";
  return "accessories";
}

function showToast(title, sub){
  const t = document.getElementById("toast");
  const tt = document.getElementById("toastTitle");
  const ts = document.getElementById("toastSub");
  if(!t || !tt || !ts) return;

  tt.textContent = title;
  ts.textContent = sub;

  t.classList.add("show");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => t.classList.remove("show"), 1700);
}

function render(){
  const wrap = document.getElementById("products");
  if(!wrap) return;

  const q = state.query.trim().toLowerCase();
  let items = state.products.slice();

  if(state.filter !== "all"){
    items = items.filter(p => categorize(p) === state.filter);
  }
  if(q){
    items = items.filter(p =>
      (p.name || "").toLowerCase().includes(q) ||
      (p.description || "").toLowerCase().includes(q)
    );
  }

  wrap.innerHTML = items.map(p => `
    <div class="ll-card">
      <div class="ll-card-top"></div>
      <div class="ll-card-body">
        <h5 class="ll-card-title">${escapeHtml(p.name || "Product")}</h5>
        <div class="ll-card-desc">${escapeHtml(p.description || "—")}</div>
        <div class="ll-card-foot">
          <div class="ll-price">${money(p.price)}</div>
          <button class="ll-add" type="button" data-id="${escapeAttr(p.id)}">
            <i class="bi bi-bag-plus"></i> Add
          </button>
        </div>
      </div>
    </div>
  `).join("");

  wrap.querySelectorAll(".ll-add").forEach(btn => {
    btn.addEventListener("click", () => {
      state.cartCount += 1;
      const c = document.getElementById("cartCount");
      if(c) c.textContent = String(state.cartCount);
      showToast("Added to cart", "Saved to your cart (demo).");
    });
  });
}

function escapeHtml(s){
  return String(s || "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");
}
function escapeAttr(s){
  return escapeHtml(s).replaceAll(" ", "");
}

async function loadProducts(){
  const skeleton = document.getElementById("skeleton");
  const products = document.getElementById("products");
  const err = document.getElementById("loadError");

  try{
    const res = await fetch(`${API_BASE}/api/v1/products`);
    const data = await res.json();
    state.products = (data && data.products) ? data.products : [];

    if(skeleton) skeleton.classList.add("d-none");
    if(err) err.classList.add("d-none");
    if(products) products.classList.remove("d-none");

    render();
  }catch(e){
    if(skeleton) skeleton.classList.add("d-none");
    if(products) products.classList.add("d-none");
    if(err) err.classList.remove("d-none");
  }
}

function hookUI(){
  const year = document.getElementById("year");
  if(year) year.textContent = String(new Date().getFullYear());

  const search = document.getElementById("search");
  if(search){
    search.addEventListener("input", (e) => {
      state.query = e.target.value || "";
      render();
    });
  }

  document.querySelectorAll(".ll-filter").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".ll-filter").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.filter = btn.dataset.filter || "all";
      render();
    });
  });
}

hookUI();
loadProducts();
