"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";


const items = [
  { href: "/", label: "Ask" },
  { href: "/library", label: "Library" },
  { href: "/evals", label: "Evals" },
  { href: "/queries", label: "Queries" },
];


export function Nav() {
  const pathname = usePathname() || "/";

  return (
    <nav className="flex items-center gap-1">
      {items.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
              active ? "bg-ink-100 text-ink-900" : "text-ink-500 hover:bg-ink-50 hover:text-ink-800"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
