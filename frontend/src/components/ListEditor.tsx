"use client";

/** Editable list of small objects (e.g. services, social links). */

export interface ListField<T> {
  key: keyof T & string;
  placeholder: string;
  type?: "text" | "url";
}

interface Props<T extends object> {
  name: string; // API field name, used to match validation errors like "services.0.name"
  label: string;
  items: T[];
  fields: ListField<T>[];
  empty: T;
  onChange: (items: T[]) => void;
  errors: Record<string, string>;
  addLabel?: string;
}

export function ListEditor<T extends object>({ name, label, items, fields, empty, onChange, errors, addLabel }: Props<T>) {
  const update = (index: number, key: keyof T, value: string) =>
    onChange(items.map((item, i) => (i === index ? { ...item, [key]: value } : item)));

  return (
    <div className="field span-2">
      <label>{label}</label>
      {items.length === 0 && <span className="hint">None added yet.</span>}
      {items.map((item, index) => (
        <div key={index}>
          <div className="list-row">
            {fields.map((field) => {
              const error = errors[`${name}.${index}.${field.key}`];
              return (
                <input
                  key={field.key}
                  type={field.type ?? "text"}
                  aria-label={`${label} ${index + 1} ${field.placeholder}`}
                  placeholder={field.placeholder}
                  value={String(item[field.key] ?? "")}
                  onChange={(e) => update(index, field.key, e.target.value)}
                  className={error ? "invalid" : ""}
                />
              );
            })}
            <button
              type="button"
              className="btn btn-secondary btn-small"
              aria-label={`Remove ${label} ${index + 1}`}
              onClick={() => onChange(items.filter((_, i) => i !== index))}
            >
              Remove
            </button>
          </div>
          {fields.map((field) => {
            const error = errors[`${name}.${index}.${field.key}`];
            return error ? (
              <div key={field.key} className="error" style={{ marginTop: -4, marginBottom: 8 }}>
                {field.placeholder}: {error}
              </div>
            ) : null;
          })}
        </div>
      ))}
      <div>
        <button type="button" className="btn btn-secondary btn-small" onClick={() => onChange([...items, { ...empty }])}>
          + {addLabel ?? "Add"}
        </button>
      </div>
    </div>
  );
}
