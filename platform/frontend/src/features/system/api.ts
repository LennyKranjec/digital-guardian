import { useQuery } from '@tanstack/react-query';

import { apiGet } from '../../shared/api/client';
import { metaSchema } from './model';

export const metaQueryKey = ['meta'] as const;

export function useMeta() {
  return useQuery({
    queryKey: metaQueryKey,
    queryFn: ({ signal }) => apiGet('/meta', metaSchema, signal),
  });
}
