const $ = (sel) => document.querySelector(sel);
const toastBox = $("#toast");
let toastTimer = 0;

function yuan(cents) {
  return (Number(cents) / 100).toFixed(2);
}

function toast(message, kind = "ok") {
  toastBox.hidden = false;
  toastBox.dataset.kind = kind;
  toastBox.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastBox.hidden = true;
  }, 4600);
}

async function api(path, options = {}, timeoutMs = 20000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text };
    }
    if (!response.ok) {
      const detail = data && data.detail;
      const message = typeof detail === "string" ? detail : "请求没有通过";
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("等得太久了，模型可能还在画。可以再试一次，或先用原图排版。");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function addressLine(contact) {
  return `${contact.recipient}  ${contact.phone}  ${contact.province}${contact.city}${contact.district}${contact.address}`;
}

function renderTicket(order, controls) {
  const article = document.createElement("article");
  article.className = "ticket";
  const img = document.createElement("img");
  img.src = order.art_url;
  img.alt = "";
  const body = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = `${order.id}  ${order.card_name || ""}`;
  const stamp = document.createElement("span");
  stamp.className = `stamp st-${order.status}`;
  stamp.textContent = order.status;
  title.append(stamp);
  const meta = document.createElement("p");
  meta.textContent = `${order.quantity} 张 · ¥${yuan(order.total)} · ${new Date(order.created_at).toLocaleString("zh-CN")}`;
  const addr = document.createElement("p");
  addr.textContent = addressLine(order.contact);
  body.append(title, meta, addr);
  if (order.contact.note) {
    const note = document.createElement("p");
    note.textContent = `备注：${order.contact.note}`;
    body.append(note);
  }
  if (order.tracking_no) {
    const track = document.createElement("p");
    track.textContent = `物流：${order.carrier || "快递"} ${order.tracking_no}`;
    body.append(track);
  }
  if (typeof controls === "function") {
    const extra = controls(order);
    if (extra) body.append(extra);
  }
  article.append(img, body);
  return article;
}
