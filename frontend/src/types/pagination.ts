export interface PaginationParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  [key: string]: unknown;
}

export interface PaginatedResponse<T> {
  data: T[];
  hasMore: boolean;
  total?: number;
}


