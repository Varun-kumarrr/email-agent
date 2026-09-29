"use client";

/** Editable list of small objects (e.g. services, social links). */

import { Icon } from "./Icon";
import { buttonClass, cx } from "./ui";

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
  emptyText?: string;
}

export function ListEditor<T extends object>({ name, label, items, fields, empty, onChange, errors, addLabel, emptyText }: Props<T>) {
  const update = (index: number, key: keyof T, value: string) =>
    onChange(items.map((item, i) => (i === index ? { ...item, [key]: value } : item)));

  return (
    <div className="@container space-y-2">
      {items.length === 0 && (
        <p className="rounded-lg border border-dashed border-slate-300 px-3 py-3 text-center text-xs text-slate-500">
          {emptyText ?? "None added yet."}
        </p>
      )}
      {items.map((item, index) => (
        <div key={index}>
          <div className="flex items-start gap-2">
            <div className={cx("grid flex-1 gap-2", fields.length > 1 && "@lg:grid-cols-2")}>
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
            </div>
            <button
              type="button"
              className="mt-1 rounded-lg p-1.5 text-slate-400 transition hover:bg-red-50 hover:text-red-600"
              aria-label={`Remove ${label} ${index + 1}`}
              onClick={() => onChange(items.filter((_, i) => i !== index))}
            >
              <Icon name="trash" />
            </button>
          </div>
          {fields.map((field) => {
            const error = errors[`${name}.${index}.${field.key}`];
            return error ? (
              <p key={field.key} className="mt-1 text-xs font-medium text-red-600">
                {field.placeholder}: {error}
              </p>
            ) : null;
          })}
        </div>
      ))}
      <button type="button" className={buttonClass("secondary", "sm")} onClick={() => onChange([...items, { ...empty }])}>
        <Icon name="plus" className="size-3.5" /> {addLabel ?? "Add"}
      </button>
    </div>
  );
}
