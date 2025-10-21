# Stromligning API Integration

This document provides specific information regarding the integration with the Stromligning API within GE-Spot.

## Supplier Configuration

The Stromligning API (`/api/prices` endpoint) requires a specific `supplier` ID to be provided when fetching price data. When configuring GE-Spot for a Danish price area (DK1 or DK2), you will be prompted to enter this supplier ID in the integration options.

The value you need to enter corresponds to the `id` field from the supplier list below (e.g. `ewii_c`, `andelenergi_c`).

## Fetching the Supplier List

The list of suppliers can change over time. You can fetch an up-to-date list directly from the Stromligning API using the following command in your terminal:

```bash
curl -X GET -H "Accept: application/json" "https://stromligning.dk/api/suppliers"
```

## Suppliers (as of April 30, 2025)

Here is the list of suppliers retrieved on the date mentioned above. Use the `id` value in the GE-Spot configuration.

*   **id:** `aal_el-net_c`, **name:** Aal El-Net A M B A
*   **id:** `cerius_c`, **name:** Cerius C
*   **id:** `dinel_c`, **name:** Dinel C
*   **id:** `el-net_kongerslev`, **name:** El-net Kongerslev
*   **id:** `elektrus_c`, **name:** Elektrus C
*   **id:** `elinor`, **name:** Elinord A/S
*   **id:** `elnet_midt_c`, **name:** Elnet midt C
*   **id:** `flow_elnet`, **name:** Flow Elnet
*   **id:** `forsyning_elnet`, **name:** Forsyning Elnet A/S
*   **id:** `gev_elnet_c`, **name:** GEV Elnet A/S
*   **id:** `hammel_elforsyning_net_as`, **name:** Hammel Elforsyning Net A/S
*   **id:** `hjerting_transformatorforening`, **name:** Hjerting Transformatorforening
*   **id:** `hurup_elvrk_net_c`, **name:** Hurup Elværk Net C
*   **id:** `ikast_el_net_as_c`, **name:** Ikast El Net A/S
*   **id:** `kimbrer_c`, **name:** Kimbrer Elnet C
*   **id:** `konstant_c`, **name:** Konstant C - 151
*   **id:** `konstant_c_245`, **name:** Konstant C - 245
*   **id:** `l-net`, **name:** L-Net
*   **id:** `laesoe_elnet_c`, **name:** Læsø Elnet A/S
*   **id:** `midtfyns_c`, **name:** Midtfyns Elforsyning A.m.b.A
*   **id:** `n1_344`, **name:** N1 A/S - 344
*   **id:** `n1_c`, **name:** N1 C
*   **id:** `netselskabet_elvaerk_331_c`, **name:** Netselskabet Elværk A/S
*   **id:** `netselskabet_elvaerk_c`, **name:** Netselskabet Elværk C - Udgået
*   **id:** `nke-elnet`, **name:** NKE-Elnet
*   **id:** `noe_net`, **name:** Nordvestjysk Elforsyning (NOE Net)
*   **id:** `nord_energi_net`, **name:** Nord Energi Net
*   **id:** `radius_c`, **name:** Radius C
*   **id:** `rah_c`, **name:** RAH C
*   **id:** `ravdex`, **name:** Ravdex
*   **id:** `sunds_net`, **name:** Sunds Net A.m.b.a
*   **id:** `tarm_elværk_net_as`, **name:** Tarm Elværk Net A/S
*   **id:** `trefor_el-net_c`, **name:** Trefor El-net C
*   **id:** `trefor_el-net_oest_c`, **name:** Trefor El-Net Øst C
*   **id:** `veksel`, **name:** Veksel C
*   **id:** `videbaek_elnet_c`, **name:** Videbæk Elnet A/S
*   **id:** `vores_elnet`, **name:** Vores Elnet C
*   **id:** `zeanet`, **name:** Zeanet
