import os
import sys
import glob
import subprocess
import time
from fastapi import FastAPI
from pydantic import BaseModel
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime


# ---------------------------
# Entrada del request
# ---------------------------
class RutRequest(BaseModel):
    rut: str


# ---------------------------
# Crear aplicación FastAPI
# ---------------------------
app = FastAPI()


# -------------------------------------------------------
# Función para verificar e instalar navegadores Playwright
# -------------------------------------------------------
def ensure_playwright_browsers():
    chromium_path = os.path.expanduser("~\\AppData\\Local\\ms-playwright\\chromium-*")
    matches = glob.glob(chromium_path)

    if matches:
        chrome_exe = os.path.join(matches[0], "chrome-win", "chrome.exe")
        if os.path.exists(chrome_exe):
            return

    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error al instalar Playwright: {e}")
        sys.exit(1)


# Instalar Playwright al iniciar el servidor
ensure_playwright_browsers()


# -------------------------------------------------------
# ENDPOINT PRINCIPAL
# -------------------------------------------------------
@app.post("/consultar_rut")
def consultar_rut(data: RutRequest):

    rutUsu = data.rut

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-infobars",
                "--disable-notifications",
                "--disable-extensions",
                "--disable-popup-blocking",
                "--disable-features=IsolateOrigins,site-per-process",
                "--window-size=1920,1080"
            ]
        )

        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-CL"
        )

        page = context.new_page()

        # Abrir portal
        page.goto("https://www2.sii.cl/stc/noauthz", timeout=30000)

        # ---------------------
        # Ingresar RUT
        try:
            page.wait_for_selector("input.rut-form", timeout=20000)
            page.fill("input.rut-form", rutUsu)
        except:
            browser.close()
            return {"error": "No se encontró el input del RUT en el SII."}

        # ---------------------
        # Click en consultar
        try:
            page.wait_for_selector('input[value="Consultar Situación Tributaria"]', timeout=20000)
            page.click('input[value="Consultar Situación Tributaria"]')
        except:
            browser.close()
            return {"error": "No se encontró el botón Consultar."}

        # ---------------------
        # Buscar mensaje de error
        try:
            page.wait_for_selector("div.input-errors", timeout=5000)
            mensaje_error = page.inner_text("div.input-errors")
        except:
            mensaje_error = ""

        # ---------------------
        # Nombre o razón social
        try:
            page.wait_for_selector("label.mb-1.font-body", timeout=5000)
            texto = page.inner_text("label.mb-1.font-body").strip()
            nombre = texto.replace("Nombre o Razón Social:", "").strip()
        except:
            nombre = ""

        # ---------------------
        # Abrir tabla
        try:
            page.wait_for_selector("button.open-btn", timeout=5000)
            page.click("button.open-btn")
        except:
            pass

        # ---------------------
        # Obtener tabla
        try:
            page.wait_for_selector("table#DataTables_Table_0", timeout=10000)
            tabla = page.evaluate("""
                () => {
                    const filas = [];
                    const tbody = document.querySelector("#DataTables_Table_0 tbody");
                    if (!tbody) return filas;

                    for (const tr of tbody.querySelectorAll("tr")) {
                        const celdas = [...tr.querySelectorAll("td")].map(td => td.innerText.trim());
                        filas.push(celdas);
                    }
                    return filas;
                }
            """)
        except:
            tabla = []

        # ---------------------
        # Buscar fila más reciente
        fila_mas_reciente = None
        fecha_mas_reciente = None

        for fila in tabla:
            try:
                fecha_str = fila[5]
                fecha_dt = datetime.strptime(fecha_str, "%d-%m-%Y")
                if fecha_mas_reciente is None or fecha_dt > fecha_mas_reciente:
                    fecha_mas_reciente = fecha_dt
                    fila_mas_reciente = fila
            except:
                continue

        browser.close()

        # -------------------------------------------------
        # RETORNO DE LA API
        # -------------------------------------------------

        return {
            "rut": rutUsu,
            "nombre": nombre,
            "mensaje_error": mensaje_error,
            "registros_totales": len(tabla),
            "fila_mas_reciente": fila_mas_reciente,
            "tabla": tabla
        }
