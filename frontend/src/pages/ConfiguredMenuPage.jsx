export default function ConfiguredMenuPage({ item }) {
  return (
    <section className="page-card">
      <p className="eyebrow">Configured report</p>
      <h2>{item?.label || "Menu"}</h2>
      <p>This menu is enabled by the current directory authorization policy.</p>
      {item?.path && <small>Route: {item.path}</small>}
    </section>
  );
}
