function workshopControls(order) {
  const row = document.createElement("div");
  row.className = "ship-row";
  const add = (label, status, extra) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = label;
    button.addEventListener("click", () => changeStatus(order.id, status, extra));
    row.append(button);
  };
  if (order.status === "待印刷") {
    add("开始印刷", "印刷中");
    add("取消订单", "已取消");
  } else if (order.status === "印刷中") {
    const carrier = document.createElement("select");
    ["顺丰", "京东物流", "邮政 EMS", "其他"].forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      carrier.append(option);
    });
    const tracking = document.createElement("input");
    tracking.placeholder = "运单号";
    tracking.maxLength = 40;
    const ship = document.createElement("button");
    ship.type = "button";
    ship.className = "secondary";
    ship.textContent = "标记已发货";
    ship.addEventListener("click", () => changeStatus(order.id, "已发货", {
      carrier: carrier.value,
      tracking_no: tracking.value.trim(),
    }));
    row.append(carrier, tracking, ship);
    add("取消订单", "已取消");
  } else if (order.status === "已发货") {
    add("标记完成", "已完成");
  }
  return row;
}

async function changeStatus(id, status, extra = {}) {
  try {
    await api(`/api/orders/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, carrier: extra.carrier || "", tracking_no: extra.tracking_no || "" }),
    });
    await loadOrders();
    toast(`订单已更新为${status}。`);
  } catch (error) {
    toast(error.message, "bad");
  }
}

async function loadOrders() {
  const data = await api("/api/orders");
  const list = $("#workshop-list");
  list.replaceChildren();
  if (!data.orders.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "还没有订单。";
    list.append(empty);
    return;
  }
  data.orders.forEach((order) => list.append(renderTicket(order, workshopControls)));
}

loadOrders().catch((error) => toast(error.message, "bad"));
