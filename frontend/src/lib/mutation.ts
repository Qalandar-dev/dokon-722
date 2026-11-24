"use client";

import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";

import { errorMessage } from "@/components/layout/states";

/** Mutation with success/error toasts and cache invalidation of the given keys. */
export function useAction<TVars, TResult>(
  fn: (vars: TVars) => Promise<TResult>,
  { success, invalidate = [] }: { success?: string; invalidate?: QueryKey[] } = {},
) {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await Promise.all(invalidate.map((key) => client.invalidateQueries({ queryKey: key })));
      if (success) toast.success(success);
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
  /** Run and report success; the error is already shown as a toast, so never throws. */
  const run = async (vars: TVars): Promise<boolean> => {
    try {
      await mutation.mutateAsync(vars);
      return true;
    } catch {
      return false;
    }
  };
  return Object.assign(mutation, { run });
}
