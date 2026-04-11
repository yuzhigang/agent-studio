interface WorkbenchPlaceholderProps {
  title: string;
  description: string;
}

export function WorkbenchPlaceholder({ title, description }: WorkbenchPlaceholderProps) {
  return (
    <section aria-label={title}>
      <h2>{title}</h2>
      <p>{description}</p>
    </section>
  );
}
