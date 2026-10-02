const state = {
  upload: null,
  card: null,
  prices: { unit: 2900, shipping: 1200 },
  providers: {},
  view: "studio",
};

function provider() {
  return document.querySelector('input[name="provider"]:checked')?.value || "photo";
}

function show(view) {
  const known = ["studio", "checkout"];
  if (!known.includes(view)) view = "studio";
  if (view === "checkout" && !state.card) {
    toast("先生成一张卡，再填写地址。", "bad");
    view = "studio";
  }
  state.view = view;
  document.querySelectorAll("[data-view]").forEach((node) => {
    node.hidden = node.dataset.view !== view;
  });
  if (location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
  if (view === "checkout") fillCheckout();
}

function setUpload(upload) {
  state.upload = upload;
  const label = $("#upload-name");
  label.hidden = false;
  label.textContent = upload.filename ? `已选：${upload.filename}` : "已选好一张照片";
  if (!state.card) {
    $("#card-empty").hidden = true;
    const img = $("#card-image");
    img.hidden = false;
    img.src = upload.url;
    img.alt = "上传的原图";
    $("#card-caption").textContent = "这是原图。生成之后会换成带卡框的印刷文件。";
    $("#card-stage").classList.remove("is-foil");
  }
}

function showCard(card) {
  state.card = card;
  $("#card-empty").hidden = true;
  const img = $("#card-image");
  img.hidden = false;
  img.src = `${card.art_url}?t=${Date.now()}`;
  img.alt = card.name;
  const copy = card.copy_source === "model" ? "招式由模型撰写" : "招式来自工坊模板";
  const how = { local: "本地文生图", external: "外部 API", photo: "原图排版" }[card.provider] || card.provider;
  $("#card-caption").textContent = `${card.meta.name} · ${card.meta.rarity} · ${how} · ${copy}`;
  $("#card-stage").classList.toggle("is-foil", card.meta.rarity === "史诗" || card.meta.rarity === "传说");
  const download = $("#download");
  download.hidden = false;
  download.href = card.art_url;
  download.download = `${card.meta.name}.png`;
  $("#order-btn").disabled = false;
  $("#prompt-details").hidden = false;
  $("#prompt-text").textContent = card.prompt;
  $("#gen-status").textContent = "印刷文件已经好了，可以下单，也可以再生成一张。";
}

async function loadRecent() {
  const data = await api("/api/cards");
  const wrap = $("#recent-wrap");
  const row = $("#recent");
  row.replaceChildren();
  if (!data.cards.length) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  data.cards.forEach((card) => {
    const button = document.createElement("button");
    button.type = "button";
    const img = document.createElement("img");
    img.src = card.art_url;
    img.alt = card.name;
    button.append(img);
    button.addEventListener("click", () => showCard(card));
    row.append(button);
  });
}

function updateProviderNote() {
  const mode = provider();
  const note = $("#provider-note");
  if (mode === "local") {
    note.textContent = state.providers.local_image
      ? "本地出图地址已配置。视觉模型若可用，会顺便写招式；否则用模板文案。"
      : "本地出图还没在部署配置里配好。可以改用原图排版。";
  } else if (mode === "external") {
    note.textContent = state.providers.external_image
      ? "外部出图密钥已配置。生成时会把提示词发给该接口。"
      : "外部出图还没配齐密钥。请在部署时写入环境变量。";
  } else {
    note.textContent = "原图排版不联网，适合先看卡牌版式，或模型暂时不可用的时候。";
  }
}

async function loadConfig() {
  const config = await api("/api/config");
  state.prices = config.prices;
  state.providers = config;
  updateProviderNote();
  updateTotal();
}

function updateTotal() {
  const qty = Math.min(20, Math.max(1, Number($("#quantity").value) || 1));
  const total = state.prices.unit * qty + state.prices.shipping;
  $("#total").textContent = `合计 ¥${yuan(total)}（单卡 ¥${yuan(state.prices.unit)} × ${qty} + 运费 ¥${yuan(state.prices.shipping)}）`;
}

function fillCheckout() {
  if (!state.card) return;
  $("#checkout-art").src = state.card.art_url;
  $("#checkout-art").alt = state.card.name;
  $("#checkout-name").textContent = state.card.meta.name;
  $("#order-fields").hidden = false;
  $("#order-success").hidden = true;
  updateTotal();
}

async function onFile(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    toast("请选择图片文件。", "bad");
    return;
  }
  if (file.size > 8 * 1024 * 1024) {
    toast("图片请小于 8MB。", "bad");
    return;
  }
  const body = new FormData();
  body.append("file", file);
  const upload = await api("/api/upload", { method: "POST", body });
  setUpload(upload);
}

async function useSample(name) {
  const upload = await api(`/api/samples/${name}`, { method: "POST" });
  setUpload(upload);
  if (!$("#item-name").value.trim()) $("#item-name").value = upload.suggested_name || "";
  if (upload.suggested_category) $("#category").value = upload.suggested_category;
}

function selectedDetected(item) {
  $("#item-name").value = item.name;
  $("#category").value = item.category || "other";
}

async function analyze() {
  if (!state.upload) {
    toast("先上传或选择一张照片。", "bad");
    return;
  }
  const mode = provider() === "external" ? "external" : "local";
  $("#analyze-btn").disabled = true;
  $("#gen-status").textContent = "正在看照片里有什么…";
  try {
    const data = await api("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        upload_id: state.upload.id,
        provider: mode,
        hint: $("#item-name").value.trim(),
      }),
    }, 90000);
    const box = $("#detected");
    box.hidden = false;
    box.replaceChildren();
    data.items.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = item.summary ? `${item.name} · ${item.summary}` : item.name;
      button.addEventListener("click", () => selectedDetected(item));
      box.append(button);
    });
    selectedDetected(data.items[0]);
    $("#gen-status").textContent = "点选识别结果，或直接改名称。";
  } catch (error) {
    toast(error.message, "bad");
    $("#gen-status").textContent = "";
  } finally {
    $("#analyze-btn").disabled = false;
  }
}

async function generate(event) {
  event.preventDefault();
  if (!state.upload) {
    toast("先上传一张装备照片。", "bad");
    return;
  }
  const name = $("#item-name").value.trim();
  if (!name) {
    toast("先写上装备名称。", "bad");
    return;
  }
  const mode = provider();
  $("#generate-btn").disabled = true;
  $("#gen-status").textContent = mode === "photo"
    ? "正在排版印刷文件…"
    : "模型绘制中。本地显卡可能要一两分钟。";
  try {
    const card = await api("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        upload_id: state.upload.id,
        name,
        category: $("#category").value,
        provider: mode,
        note: $("#note").value.trim(),
      }),
    }, 200000);
    showCard(card);
    await loadRecent();
    toast("卡牌好了。");
  } catch (error) {
    toast(error.message, "bad");
    $("#gen-status").textContent = "这次没有生成成功。";
  } finally {
    $("#generate-btn").disabled = false;
  }
}

async function submitOrder(event) {
  event.preventDefault();
  if (!state.card) return;
  const payload = {
    card_id: state.card.id,
    quantity: Number($("#quantity").value),
    recipient: $("#recipient").value.trim(),
    phone: $("#phone").value.trim(),
    province: $("#province").value.trim(),
    city: $("#city").value.trim(),
    district: $("#district").value.trim(),
    address: $("#address").value.trim(),
    postal_code: $("#postal").value.trim(),
    note: $("#order-note").value.trim(),
  };
  if (!/^1[3-9]\d{9}$/.test(payload.phone)) {
    toast("请填写 11 位手机号。", "bad");
    return;
  }
  $("#submit-order").disabled = true;
  try {
    const order = await api("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    $("#order-fields").hidden = true;
    $("#order-success").hidden = false;
    $("#success-id").textContent = order.id;
    $("#success-total").textContent = `${order.quantity} 张 · 合计 ¥${yuan(order.total)} · ${order.status}`;
    $("#success-address").textContent = addressLine(order.contact);
    toast("订单已提交。");
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    $("#submit-order").disabled = false;
  }
}

function bind() {
  const input = $("#file-input");
  const drop = $("#dropzone");
  drop.addEventListener("click", () => input.click());
  drop.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
  });
  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    onFile(file).catch((error) => toast(error.message, "bad"));
    input.value = "";
  });
  ["dragover", "dragenter"].forEach((name) => {
    drop.addEventListener(name, (event) => {
      event.preventDefault();
      drop.classList.add("is-hot");
    });
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("is-hot"));
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("is-hot");
    const file = event.dataTransfer.files && event.dataTransfer.files[0];
    onFile(file).catch((error) => toast(error.message, "bad"));
  });

  document.querySelectorAll("[data-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      useSample(button.dataset.sample).catch((error) => toast(error.message, "bad"));
    });
  });
  $("#analyze-btn").addEventListener("click", analyze);
  $("#make-form").addEventListener("submit", generate);
  document.querySelectorAll('input[name="provider"]').forEach((node) => {
    node.addEventListener("change", updateProviderNote);
  });
  $("#order-btn").addEventListener("click", () => show("checkout"));
  $("#back-studio").addEventListener("click", () => show("studio"));
  $("#quantity").addEventListener("input", updateTotal);
  $("#order-form").addEventListener("submit", submitOrder);
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
}

bind();
show(location.hash.slice(1) || "studio");
loadConfig().catch((error) => toast(error.message, "bad"));
loadRecent().catch(() => {});
