/** Shapes returned by the FastAPI backend (see /api/v1/docs). Money is a decimal string. */

export type Money = string;
export type UUID = string;

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export type Permission =
  | "dashboard.view"
  | "reports.view"
  | "products.view"
  | "products.manage"
  | "categories.manage"
  | "inventory.view"
  | "inventory.manage"
  | "orders.view"
  | "orders.manage"
  | "orders.refund"
  | "customers.view"
  | "customers.manage"
  | "promo.manage"
  | "delivery.manage"
  | "staff.manage"
  | "settings.manage"
  | "audit.view";

export interface AdminMe {
  id: UUID;
  email: string;
  full_name: string;
  role: string;
  role_title: string;
  permissions: Permission[];
}

export interface TokenOut {
  access_token: string;
  expires_at: string;
  admin: AdminMe;
}

export type OrderStatus =
  | "pending"
  | "confirmed"
  | "processing"
  | "shipped"
  | "out_for_delivery"
  | "delivered"
  | "cancelled"
  | "refunded";
export type PaymentStatus = "pending" | "processing" | "paid" | "failed" | "cancelled" | "refunded";
export type DeliveryStatus =
  | "awaiting_dispatch"
  | "preparing"
  | "shipped"
  | "out_for_delivery"
  | "delivered"
  | "delivery_failed"
  | "returned";
export type PaymentMethod = "click" | "payme" | "cash_on_delivery";

export interface Labels {
  status: string;
  payment_status: string;
  delivery_status: string;
}

export interface OrderListItem {
  id: UUID;
  number: string;
  status: OrderStatus;
  payment_status: PaymentStatus;
  delivery_status: DeliveryStatus;
  payment_method: PaymentMethod;
  labels: Labels;
  total: Money;
  items_count: number;
  created_at: string;
  user_id: UUID;
  recipient_name: string;
  recipient_phone: string;
  region_name: string;
  district_name: string;
}

export interface OrderItem {
  id: UUID;
  product_id: UUID | null;
  variant_id: UUID | null;
  product_name: string;
  variant_name: string;
  sku: string;
  attributes: Record<string, string>;
  original_unit_price: Money;
  unit_price: Money;
  quantity: number;
  line_total: Money;
}

export interface HistoryEntry {
  field: "status" | "payment_status" | "delivery_status";
  from_value: string | null;
  to_value: string;
  actor_type: "admin" | "customer" | "system" | "provider";
  admin_user_id: UUID | null;
  comment: string | null;
  created_at: string;
}

export interface PaymentAttempt {
  id: UUID;
  order_id: UUID;
  provider: "click" | "payme" | "cash" | "mock";
  amount: Money;
  status: PaymentStatus;
  is_simulated: boolean;
  failure_reason: string | null;
  created_at: string;
  paid_at: string | null;
}

export interface AdminOrder extends OrderListItem {
  subtotal: Money;
  discount_total: Money;
  delivery_fee: Money;
  promo_code: string | null;
  address_line: string;
  landmark: string | null;
  delivery_instructions: string | null;
  delivery_method_name: string;
  delivery_eta_min_days: number | null;
  delivery_eta_max_days: number | null;
  pickup_address: string | null;
  customer_note: string | null;
  cancel_reason: string | null;
  internal_note: string | null;
  stock_state: string;
  paid_at: string | null;
  confirmed_at: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
  cancelled_at: string | null;
  reservation_expires_at: string | null;
  items: OrderItem[];
  history: HistoryEntry[];
  payments: PaymentAttempt[];
}

export interface Image {
  id: UUID;
  url: string;
  alt_text: string | null;
  is_main: boolean;
  sort_order: number;
}

export interface AdminVariant {
  id: UUID;
  sku: string;
  name: string;
  attributes: Record<string, string>;
  price: Money;
  discount_price: Money | null;
  barcode: string | null;
  ikpu_code: string | null;
  package_code: string | null;
  weight_grams: number | null;
  is_default: boolean;
  is_active: boolean;
  sort_order: number;
  on_hand: number;
  reserved: number;
  available: number;
  low_stock_threshold: number | null;
}

export interface AdminProduct {
  id: UUID;
  name: string;
  slug: string;
  description: string | null;
  brand: string | null;
  category_id: UUID;
  category_name: string | null;
  is_active: boolean;
  is_featured: boolean;
  sold_count: number;
  image_url: string | null;
  images: Image[];
  variants: AdminVariant[];
  created_at: string;
  updated_at: string;
}

export interface AdminCategory {
  id: UUID;
  parent_id: UUID | null;
  name: string;
  slug: string;
  description: string | null;
  image_url: string | null;
  sort_order: number;
  is_active: boolean;
  products_count: number;
}

export interface StockRow {
  variant_id: UUID;
  product_id: UUID;
  product_name: string;
  variant_name: string;
  sku: string;
  is_active: boolean;
  on_hand: number;
  reserved: number;
  available: number;
  low_stock_threshold: number | null;
  is_low: boolean;
}

export interface Movement {
  id: UUID;
  type: string;
  on_hand_delta: number;
  reserved_delta: number;
  on_hand_after: number;
  reserved_after: number;
  reason: string | null;
  order_id: UUID | null;
  admin_user_id: UUID | null;
  created_at: string;
}

export interface Customer {
  id: UUID;
  telegram_id: number;
  first_name: string;
  last_name: string | null;
  username: string | null;
  phone: string | null;
  phone_verified: boolean;
  is_blocked: boolean;
  orders_count: number;
  total_spent: Money;
  last_order_at: string | null;
  created_at: string;
}

export interface Promo {
  id: UUID;
  code: string;
  description: string | null;
  discount_type: "percent" | "fixed";
  value: Money;
  max_discount: Money | null;
  min_order_amount: Money;
  starts_at: string;
  ends_at: string | null;
  usage_limit: number | null;
  per_user_limit: number | null;
  used_count: number;
  is_active: boolean;
  created_at: string;
}

export interface Region {
  id: number;
  code: string;
  name: string;
  sort_order: number;
  is_active: boolean;
  districts_count: number;
}

export interface District {
  id: number;
  region_id: number;
  code: string;
  name: string;
  kind: "district" | "city";
  sort_order: number;
  is_active: boolean;
}

export interface DeliveryMethod {
  id: UUID;
  code: string;
  kind: "courier" | "pickup" | "postal";
  name: string;
  description: string | null;
  sort_order: number;
  is_active: boolean;
}

export interface DeliveryRate {
  id: UUID;
  method_id: UUID;
  method_name: string;
  region_id: number;
  region_name: string;
  district_id: number | null;
  district_name: string | null;
  price: Money;
  free_threshold: Money | null;
  eta_min_days: number;
  eta_max_days: number;
  pickup_address: string | null;
  is_active: boolean;
}

export interface Staff {
  id: UUID;
  email: string;
  full_name: string;
  role: string;
  role_title: string;
  telegram_id: number | null;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface Role {
  id: number;
  name: string;
  title: string;
  permissions: Permission[];
}

export interface AuditEntry {
  id: UUID;
  admin_user_id: UUID | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  changes: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface RevenueStat {
  revenue: Money;
  orders: number;
}

export interface LowStock {
  variant_id: UUID;
  product_id: UUID;
  product_name: string;
  variant_name: string;
  sku: string;
  on_hand: number;
  reserved: number;
  available: number;
  threshold: number;
}

export interface Dashboard {
  revenue_total: Money;
  revenue_today: RevenueStat;
  revenue_week: RevenueStat;
  revenue_month: RevenueStat;
  orders_total: number;
  orders_pending: number;
  orders_in_progress: number;
  orders_completed: number;
  orders_cancelled: number;
  customers_total: number;
  customers_new_month: number;
  low_stock: LowStock[];
  best_sellers: { product_id: UUID | null; product_name: string; units: number; revenue: Money }[];
  sales_chart: { period: string; orders: number; revenue: Money; average_order: Money }[];
}
