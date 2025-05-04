using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using DG.Tweening;
using NaughtyAttributes;
using TMPro;
using UnityEngine;

namespace Wyvern
{
	// Token: 0x02000391 RID: 913
	public partial class TextRender : BaseRender
	{
		// Token: 0x06001E45 RID: 7749
		public static string WordWrap(string text, int lineCharacter, int allowNum, ref int textCount, bool commandReplace = true)
		{
			if (text == null)
			{
				return "";
			}
			string text2 = "";
			int i = 0;
			int num = 0;
			lineCharacter = 70;
			int num2 = lineCharacter;
			textCount = 0;
			text = new Regex("\n\u3000").Replace(text, "\n");
			if (commandReplace)
			{
				TextRender.textCommandList.ForEach(delegate(string value)
				{
					text = new Regex(value).Replace(text, "");
				});
			}
			while (i < text.Length)
			{
				while (i < text.Length && text[i] == '_')
				{
					for (int j = 0; j < 2; j++)
					{
						text2 += text[i].ToString();
						i++;
						num++;
						num2++;
					}
				}
				if (num > num2 && text[i] != '\n')
				{
					// Back-track so we don’t split an ASCII word
					while (i > 0 && text[i - 1] <= '\u007f' && text[i] <= '\u007f' && text[i - 1] != ' ' && text[i - 1] != '\u3000')
					{
						i--;
						text2 = text2.Remove(text2.Length - 1);
						num--;
					}
					int num3 = -1;
					int num4 = 0;
					while (num4 < allowNum && text.Length > i + num4)
					{
						if (Array.IndexOf<char>(TextRender.kinsokuHead, text[i + num4]) >= 0)
						{
							num3 = num4;
						}
						num4++;
					}
					if (Array.IndexOf<char>(TextRender.kinsokuEnd, text[i]) >= 0)
					{
						int num5 = 0;
						while (num5 < allowNum && text.Length > i + num5)
						{
							if (Array.IndexOf<char>(TextRender.kinsokuHead, text[i + num5]) >= 0)
							{
								num3 = num5;
								break;
							}
							num5++;
						}
					}
					if (num3 >= 0 && text.Length > i + num3 + 1 && Array.IndexOf<char>(TextRender.kinsokuHead, text[i + num3 + 1]) < 0)
					{
						bool flag = false;
						for (int k = 0; k <= num3; k++)
						{
							if (i >= text.Length)
							{
								flag = true;
								break;
							}
							text2 += text[i].ToString();
							i++;
							textCount++;
						}
						if (flag)
						{
							break;
						}
					}
					else if (num3 >= 0 && text.Length > i + num3 && text.Length <= i + num3)
					{
						for (int l = 0; l <= num3; l++)
						{
							text2 += text[i].ToString();
							i++;
							textCount++;
						}
						if (i < text.Length && Array.IndexOf<char>(TextRender.kinsokuHead, text[i]) > 0)
						{
							text2 += text[i].ToString();
							textCount++;
							break;
						}
						break;
					}
					if (text[i] != '\n')
					{
						text2 += "\n";
						num = 0;
						num2 = lineCharacter;
					}
				}
				if (text[i] == '\n')
				{
					num = 0;
					num2 = lineCharacter;
				}
				text2 += text[i].ToString();
				i++;
				num++;
				textCount++;
				while (i < text.Length && text[i] == '<')
				{
					bool flag2 = false;
					string text3 = "";
					List<string> list = new List<string>();
					while (i < text.Length)
					{
						char c = text[i];
						if (c == '<')
						{
							flag2 = true;
						}
						else if (c == '>')
						{
							text3 += c.ToString();
							if (Regex.IsMatch(text3, "<sprite") || Regex.IsMatch(text3, "<space") || Regex.IsMatch(text3, "<line-height"))
							{
								flag2 = false;
							}
							else if (Regex.IsMatch(text3, "</"))
							{
								list.RemoveAt(list.Count - 1);
								if (list.Count == 0)
								{
									flag2 = false;
								}
							}
							else
							{
								list.Add(text3);
							}
							text3 = "";
						}
						if (flag2)
						{
							text3 += c.ToString();
						}
						text2 += text[i].ToString();
						i++;
						num++;
						num2++;
						if (!flag2)
						{
							break;
						}
					}
				}
			}
			return text2;
		}
	}
}
