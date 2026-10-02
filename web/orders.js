async function loadOrders() {
  const data = await api("/api/orders");
  const list = $("#orders-list");
  list.replaceChildren();
  if (!data.orders.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "还没有订单。";
    list.append(empty);
    return;
  }
  data.orders.forEach((order) => list.append(renderTicket(order)));
}

loadOrders().catch((error) => toast(error.message, "bad"));
