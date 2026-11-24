"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";

export function Pagination({
  page,
  pages,
  total,
  onChange,
}: {
  page: number;
  pages: number;
  total: number;
  onChange: (page: number) => void;
}) {
  return (
    <div className="text-muted-foreground mt-3 flex items-center justify-between text-sm">
      <span>Jami: {total}</span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          aria-label="Oldingi sahifa"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          <ChevronLeft />
        </Button>
        <span>
          {page} / {Math.max(pages, 1)}
        </span>
        <Button
          variant="outline"
          size="icon"
          aria-label="Keyingi sahifa"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}
