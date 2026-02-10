# 🔐 Payment Permission Fix - RESOLVED

## Problem

**Error:** `403 Forbidden` when tenants try to make payments

**Cause:** The `PaymentViewSet` inherited permissions from `BaseViewSet` which only allowed:
- ✅ Admins: Full access
- ✅ Property Managers: Full access  
- ❌ Tenants: **Read-only access** (GET only)

Tenants couldn't POST to `/api/finance/payments/quick_payment/`

---

## Solution

### 1. Override Permissions for quick_payment

**File:** `finance/views.py` - `PaymentViewSet`

```python
def get_permissions(self):
    """
    Override permissions to allow tenants to make payments.
    Tenants can POST to quick_payment, but still read-only for list/retrieve.
    """
    if self.action == 'quick_payment':
        # Allow authenticated users (including tenants) to make payments
        return [IsAuthenticated()]
    return super().get_permissions()
```

**Result:** Tenants can now POST to `quick_payment` endpoint!

### 2. Add Security Check

**File:** `finance/views.py` - `quick_payment()` method

```python
# Security: Tenants can only make payments for themselves
if request.user.role == 'tenant':
    if not hasattr(request.user, 'tenant_profile'):
        return Response(
            {'error': 'User does not have a tenant profile'},
            status=status.HTTP_403_FORBIDDEN
        )
    if request.user.tenant_profile.id != tenant.id:
        return Response(
            {'error': 'You can only make payments for yourself'},
            status=status.HTTP_403_FORBIDDEN
        )
```

**Security:** Tenants can ONLY make payments for their own account, not for others!

---

## Permissions Matrix (After Fix)

| User Role | List Payments | View Payment | Create Payment | Quick Payment | Process Payment |
|-----------|---------------|--------------|----------------|---------------|-----------------|
| **Tenant** | Read Own | Read Own | ❌ | ✅ Own Only | ❌ |
| **Property Manager** | Read Managed | Read Managed | ✅ | ✅ | ✅ |
| **Admin** | ✅ All | ✅ All | ✅ | ✅ | ✅ |

---

## Testing

### ✅ Tenant Can Make Payment (Should Work Now)

```bash
curl -X POST http://localhost:8000/api/finance/payments/quick_payment/ \
  -H "Authorization: Bearer TENANT_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": 1,
    "invoice_id": 5,
    "payment_method": "bank_transfer"
  }'
```

**Expected Response:** `201 Created` with payment, receipt, and invoice data

### ❌ Tenant Cannot Pay for Other Tenant (Should Fail)

```bash
curl -X POST http://localhost:8000/api/finance/payments/quick_payment/ \
  -H "Authorization: Bearer TENANT_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": 999,
    "invoice_id": 5,
    "payment_method": "bank_transfer"
  }'
```

**Expected Response:** `403 Forbidden` - "You can only make payments for yourself"

### ✅ Admin/Manager Can Pay for Any Tenant (Should Work)

```bash
curl -X POST http://localhost:8000/api/finance/payments/quick_payment/ \
  -H "Authorization: Bearer ADMIN_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": 1,
    "invoice_id": 5,
    "payment_method": "cash"
  }'
```

**Expected Response:** `201 Created`

---

## Frontend Integration

### Before (Failed)
```javascript
// ❌ Got 403 Forbidden
const response = await fetch('/api/finance/payments/quick_payment/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${tenantToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    tenant_id: currentTenantId,
    invoice_id: invoiceId,
    payment_method: 'bank_transfer'
  })
})
```

### After (Works!)
```javascript
// ✅ Now returns 201 Created
const response = await fetch('/api/finance/payments/quick_payment/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${tenantToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    tenant_id: currentTenantId,  // Must match logged-in tenant
    invoice_id: invoiceId,
    payment_method: 'bank_transfer'
  })
})

if (response.ok) {
  const data = await response.json()
  console.log('Payment successful!')
  console.log('Reference:', data.payment.reference_number)
  console.log('Receipt:', data.receipt.receipt_number)
}
```

---

## Security Features

1. **Authentication Required:** Must have valid JWT token
2. **Tenant Validation:** Tenants can only pay for themselves
3. **Invoice Ownership:** Invoice must belong to the tenant
4. **Amount Validation:** Can't overpay invoice balance
5. **Atomic Transactions:** All-or-nothing processing

---

## Common Errors & Solutions

### Error: "403 Forbidden"
**Cause:** Token expired or invalid
**Solution:** Refresh token using `/api/token/refresh/`

### Error: "You can only make payments for yourself"
**Cause:** Tenant trying to pay for another tenant
**Solution:** Use correct `tenant_id` matching logged-in user

### Error: "Invoice does not belong to this tenant"
**Cause:** Wrong invoice ID for the tenant
**Solution:** Verify invoice belongs to the tenant first

### Error: "Payment amount exceeds invoice balance"
**Cause:** Trying to pay more than owed
**Solution:** Check `invoice.balance_due` first

---

## Status: ✅ FIXED

Tenants can now make payments successfully while maintaining proper security!

**Changes Made:**
1. ✅ Override permissions for `quick_payment` endpoint
2. ✅ Add tenant-self security check
3. ✅ Maintain read-only permissions for list/retrieve
4. ✅ Allow admins and managers full access

**Try it now!** Your payment should work. 🚀

