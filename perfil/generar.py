import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "perfil" / "proyectos.yml"
README = RAIZ / "README.md"
INICIO = "<!-- PROYECTOS:INICIO -->"
FIN = "<!-- PROYECTOS:FIN -->"
API = "https://api.github.com"
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


class NoEncontrado(Exception):
    pass


def api(ruta):
    peticion = urllib.request.Request(API + ruta)
    peticion.add_header("Accept", "application/vnd.github+json")
    peticion.add_header("X-GitHub-Api-Version", "2022-11-28")
    token = os.environ.get("GH_TOKEN")
    if token:
        peticion.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            return json.load(respuesta)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise NoEncontrado(ruta) from None
        raise


def mis_repos(usuario):
    repos, pagina = [], 1
    ruta = "/user/repos?affiliation=owner&per_page=100&page={}" if os.environ.get("GH_TOKEN") else f"/users/{usuario}/repos?per_page=100&page={{}}"
    while True:
        try:
            lote = api(ruta.format(pagina))
        except urllib.error.HTTPError:
            if ruta.startswith("/user/"):
                ruta = f"/users/{usuario}/repos?per_page=100&page={{}}"
                continue
            raise
        repos.extend(lote)
        if len(lote) < 100:
            return repos
        pagina += 1


def clave_version(nombre):
    return [int(n) for n in re.findall(r"\d+", nombre)] or [-1]


def version(usuario, repo):
    try:
        return api(f"/repos/{usuario}/{repo}/releases/latest")["tag_name"]
    except (NoEncontrado, urllib.error.HTTPError):
        pass
    try:
        etiquetas = [e["name"] for e in api(f"/repos/{usuario}/{repo}/tags?per_page=100")]
    except (NoEncontrado, urllib.error.HTTPError):
        return None
    return max(etiquetas, key=clave_version) if etiquetas else None


def escapar(texto):
    return urllib.parse.quote(str(texto).replace("-", "--").replace("_", "__").replace(" ", "_"), safe="")


def insignia(etiqueta, valor, color, logo=None):
    url = f"https://img.shields.io/badge/{escapar(etiqueta)}-{escapar(valor)}-{color}?style=flat-square"
    if logo:
        url += f"&logo={logo}"
    return f'<img src="{url}" alt="{etiqueta}: {valor}"/>'


def mes(fecha):
    if not fecha:
        return None
    anio, numero = fecha[:4], int(fecha[5:7])
    return f"{MESES[numero - 1]} {anio}"


def datos_repo(usuario, item, listado):
    nombre = item["repo"]
    info = listado.get(nombre.lower())
    if info is None:
        try:
            info = api(f"/repos/{usuario}/{nombre}")
        except NoEncontrado:
            print(f"aviso: {nombre} no es visible con este token; se muestra como privado", file=sys.stderr)
            info = {"name": nombre, "private": True}
    return {
        "titulo": item.get("titulo") or info.get("name", nombre),
        "emoji": item.get("emoji", "📦"),
        "url": info.get("html_url") if not info.get("private") else None,
        "privado": bool(info.get("private")),
        "archivado": bool(info.get("archived")),
        "estrellas": info.get("stargazers_count") or 0,
        "version": version(usuario, info.get("name", nombre)) or item.get("version"),
        "actualizado": mes(info.get("pushed_at")),
        "resumen": item.get("resumen") or info.get("description") or "",
        "puntos": item.get("puntos") or [],
        "stack": item.get("stack") or ([info["language"]] if info.get("language") else []),
        "estado": item.get("estado"),
        "nota": item.get("nota"),
        "es_repo": True,
    }


def datos_servicio(item):
    return {
        "titulo": item["servicio"],
        "emoji": item.get("emoji", "🌐"),
        "url": item.get("url"),
        "privado": False,
        "archivado": False,
        "estrellas": 0,
        "version": item.get("version"),
        "actualizado": None,
        "resumen": item.get("resumen", ""),
        "puntos": item.get("puntos") or [],
        "stack": item.get("stack") or [],
        "estado": item.get("estado"),
        "nota": item.get("nota"),
        "es_repo": False,
    }


def tarjeta(p, ancho):
    titulo = f'<a href="{p["url"]}">{p["titulo"]}</a>' if p["url"] else p["titulo"]
    insignias = []
    if p["version"]:
        insignias.append(insignia("versión", p["version"], "0e75b6"))
    if p["estado"]:
        insignias.append(insignia("estado", p["estado"], "f0a500"))
    if p["archivado"]:
        insignias.append(insignia("archivado", "sí", "6e7681"))
    if p["es_repo"]:
        if p["privado"]:
            insignias.append(insignia("repo", "privado", "555", "github"))
        else:
            insignias.append(insignia("repo", "público", "00b37e", "github"))
    else:
        insignias.append(insignia("servicio", "público", "00b37e"))
    if p["estrellas"] and not p["privado"]:
        insignias.append(insignia("★", p["estrellas"], "f5c518"))
    if p["actualizado"]:
        insignias.append(insignia("actualizado", p["actualizado"], "30363d"))

    lineas = [
        f'<td width="{ancho}" valign="top">',
        "",
        f'### {p["emoji"]} {titulo}',
        " ".join(insignias),
        "",
        p["resumen"].strip(),
        "",
    ]
    if p["puntos"]:
        lineas += [f"- {punto}" for punto in p["puntos"]] + [""]
    if p["url"] and not p["es_repo"]:
        lineas += [f'🔗 **[{p["url"].split("://", 1)[-1]}]({p["url"]})**', ""]
    if p["nota"]:
        lineas += [f'<sub>{p["nota"]}</sub>', ""]
    if p["privado"]:
        lineas += ["<sub>🔒 Repositorio privado: si te interesa, escríbeme y te doy acceso.</sub>", ""]
    if p["stack"]:
        lineas += [" ".join(f"`{s}`" for s in p["stack"]), ""]
    lineas.append("</td>")
    return "\n".join(lineas)


def seccion(proyectos):
    privados = sum(1 for p in proyectos if p["es_repo"] and p["privado"])
    publicos = sum(1 for p in proyectos if p["es_repo"] and not p["privado"])
    partes = [INICIO, "", "<!-- Sección generada por perfil/generar.py: edita perfil/proyectos.yml, no este bloque -->", ""]
    partes += [
        '<p align="center">',
        "  " + insignia("repos públicos", publicos, "00b37e", "github"),
        "  " + insignia("repos privados", privados, "555", "github"),
        "</p>",
        "",
    ]
    if privados:
        partes += [
            "> [!NOTE]",
            "> Algunos repositorios son **privados** (varios de forma temporal) mientras maduran.",
            "> Si te interesa alguno, escríbeme y te cuento más o te doy acceso.",
            "",
        ]
    partes.append("<table>")
    for i in range(0, len(proyectos), 2):
        fila = proyectos[i:i + 2]
        partes.append("<tr>")
        if len(fila) == 2:
            partes += [tarjeta(fila[0], "50%"), tarjeta(fila[1], "50%")]
        else:
            partes.append(tarjeta(fila[0], "100%").replace('<td width="100%"', '<td colspan="2" width="100%"', 1))
        partes.append("</tr>")
    partes += ["</table>", "", FIN]
    return "\n".join(partes)


def main():
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    usuario = config["usuario"]
    topic = config.get("topic_auto")
    repos = mis_repos(usuario)
    listado = {r["name"].lower(): r for r in repos}

    proyectos, vistos = [], set()
    for item in config.get("proyectos") or []:
        if item.get("mostrar") is False:
            vistos.add(str(item.get("repo", "")).lower())
            continue
        if "repo" in item:
            vistos.add(item["repo"].lower())
            proyectos.append(datos_repo(usuario, item, listado))
        elif "servicio" in item:
            proyectos.append(datos_servicio(item))

    if topic:
        for r in sorted(repos, key=lambda r: r.get("pushed_at") or "", reverse=True):
            if r["name"].lower() in vistos or r.get("fork") or topic not in (r.get("topics") or []):
                continue
            proyectos.append(datos_repo(usuario, {"repo": r["name"]}, listado))

    texto = README.read_text(encoding="utf-8")
    if INICIO not in texto or FIN not in texto:
        sys.exit(f"README.md no tiene los marcadores {INICIO} y {FIN}")
    antes, resto = texto.split(INICIO, 1)
    _, despues = resto.split(FIN, 1)
    nuevo = antes + seccion(proyectos) + despues
    if nuevo != texto:
        README.write_text(nuevo, encoding="utf-8")
        print("README.md actualizado")
    else:
        print("Sin cambios")


if __name__ == "__main__":
    main()
