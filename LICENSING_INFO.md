# GuardPrompt Licensing Model

GuardPrompt is licensed as an **annual on-premise subscription**, based on the organization's size.  
The customer manages how many internal users access the system.

GuardPrompt does **not** count or track active users.

---

## Organization Size Tiers

Organizations choose a subscription tier based on their approximate size:

- **Small (S):** up to 50 employees  
- **Medium (M):** 51–250 employees  
- **Large (L):** 251–1000 employees  
- **Enterprise (XL):** 1001–5000+ employees  

These tiers are used only for pricing purposes — the organization regulates its own user count.

---

## What’s Included in the Annual License

- Unlimited documents  
- Unlimited anonymization and ingestion  
- Unlimited RAG / AI queries  
- Full access to OpenWebUI integrations  
- GPU acceleration support  
- All updates and security patches  
- On-premise deployment rights  

---

## What’s Not Included

External AI service fees (if used) are **not** covered by the GuardPrompt license.  
This includes:

- OpenRouter.ai  
- OpenAI API  
- Anthropic Claude  
- Gemini  
- Mistral  
- Any other third-party LLM provider  

These services are billed separately by their providers.

---

## Trial License (30 Days)

- Valid for 30 days  
- Up to 3 users  
- Unlimited documents  
- Full functionality  
- After expiration, the system enters **Restricted Mode** until a commercial license is applied  

## Trial License Activation

To activate the 30-day trial license, the customer must provide specific registration information to the GuardPrompt vendor.

### Required Registration Information

Info for Anonymizer Registration:
- Host ID: provided automatically
- Host IP: provided automatically
- Data Till: will be set automatically
- Admin Email: (entered by user)
- Admin Pass: (entered by user)
- Users Count: 3

### Retrieving Host ID and Host IP

GuardPrompt exposes a local endpoint that automatically provides the required machine identifiers:

http://localhost:8005/api/reginfo

This endpoint returns or requires the following fields:

- **Host ID** – a unique hardware-bound identifier of the anonymizer instance. Used to generate a license that is cryptographically tied to this installation, preventing unauthorized reuse.
- **Host IP** – the server’s external IP address detected at registration time. Used for license validation and security auditing to ensure the license belongs to the correct organization.
- **Data Till** – the trial license expiration date. This field is automatically set by the vendor when generating the trial license (30 days from activation). Users do not modify this value.
- **Admin Email** – entered by the customer. This becomes the primary administrator account used to count GuardPrompt users and settings.
- **Admin Pass** – entered by the customer. A secure password chosen for the administrator account. The vendor does not set or know this password.
- **Users Count: 3** – fixed limit for the trial license. The trial version supports up to three internal users (administrator + administrator/standart + administrator/standart user). Increasing this value requires a commercial license.

### Admin Credentials

During registration, the customer must provide:

- **Admin Email** – the primary administrator account  
- **Admin Password** – chosen during initial setup  
- **Users Count** – fixed at **3** for the trial license  

No additional configuration is required.

### License Delivery

Once the vendor receives the registration information, a trial license key is generated and provided to the customer.  
Applying the key activates the full **30-day trial period**, enabling all platform features.

After the trial expires, GuardPrompt automatically enters **Restricted Mode** until a commercial license is applied.

For license delivery and support, contact:

- **Telegram:** [@GuardPrompt](https://t.me/GuardPrompt)  
- **Email:** [info@guardprompt.lt](mailto:info@guardprompt.lt)

---

## Renewal

Licenses are typically renewed on an **annual basis (minimum 12 months)**.  
However, the subscription period can be customized — the vendor and customer may agree on **any license duration**, such as:

- 12 months (standard)
- 18 months
- 24 months
- 36 months
- Custom enterprise term

If a license expires, GuardPrompt remains installed but enters **Restricted Mode** until a new license is activated.

---

## License Responsibility

The customer is responsible for:

- managing internal access  
- ensuring that user count aligns with the chosen subscription tier  
- preventing external or third-party access  

GuardPrompt enforces the licensed user limit. If the number of configured users exceeds the number allowed by the license tier, the system automatically enters **Restricted Mode**, and normal functionality is disabled until the issue is resolved.

The organization must ensure that the number of active user accounts does not exceed the licensed amount.

