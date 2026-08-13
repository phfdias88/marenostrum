/**
 * Download de arquivo binario vindo da API.
 *
 * POR QUE ESTE HELPER EXISTE (bug de producao, ago/2026):
 * revogar a object URL na MESMA volta do event loop em que se chama a.click()
 * cancela o download silenciosamente. O navegador so comeca a LER o blob na
 * tarefa seguinte; se a URL ja foi revogada, ele desiste sem erro nenhum.
 * O sintoma e cruel pra depurar: o servidor registra 200 com o arquivo inteiro
 * (o dossie chegou a sair daqui com 8 paginas) e o usuario jura que "nao gera"
 * — porque nada aparece na tela nem no console.
 *
 * Aqui a revogacao fica adiada, e a URL e devolvida pra quem chamou poder
 * oferecer um "Abrir" caso o navegador tenha barrado o download automatico
 * (Opera/Chrome bloqueiam por origem, e a origem mudou no corte pro dominio).
 */
export function saveBlob(blob: Blob, filename: string): string {
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();

  // 2 min: tempo de sobra pro download comecar e pro usuario clicar no "Abrir"
  // do toast. Revogar antes disso e o que quebrava.
  setTimeout(() => URL.revokeObjectURL(url), 120_000);

  return url;
}

/** Mensagem de erro que diz o que fazer, em vez de "erro no servidor". */
export function downloadErrorMessage(status: number | null): string {
  switch (status) {
    case 401:
      return "Sua sessao expirou. Entre de novo e tente outra vez.";
    case 403:
      return "Seu acesso nao inclui este relatorio.";
    case 404:
      return "Candidato nao encontrado para gerar o relatorio.";
    case 429:
      return "Muitos downloads seguidos. Aguarde um minuto e tente de novo.";
    default:
      return status && status >= 500
        ? "O servidor falhou ao montar o arquivo. Tente de novo em instantes."
        : "Nao foi possivel baixar o arquivo. Verifique sua conexao.";
  }
}
