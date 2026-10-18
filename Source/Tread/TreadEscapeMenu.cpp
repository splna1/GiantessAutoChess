#include "TreadEscapeMenu.h"

#include "TreadUIStyle.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Images/SImage.h"

namespace
{
	FSlateFontInfo MenuFont(TreadUI::EFontRole Role, float SizePt)
	{
		return TreadUI::Font(Role, SizePt);
	}
}

void STreadEscapeMenu::Construct(const FArguments& InArgs)
{
	OnQuit = InArgs._OnQuit;
	OnCancel = InArgs._OnCancel;

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		.HAlign(HAlign_Fill)
		.VAlign(VAlign_Fill)
		[
			// Dim the whole viewport; also swallows clicks so the board behind cannot be played while open.
			SNew(SButton)
			.ButtonColorAndOpacity(FLinearColor(0.0f, 0.0f, 0.0f, 0.72f))
			.OnClicked_Lambda([this]() { return FReply::Handled(); })
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Center)
		[
			SNew(SBox)
			.WidthOverride(560.0f)
			[
				SNew(SBorder)
				.BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush"))
				.BorderBackgroundColor(TreadUI::Paper)
				.Padding(FMargin(34.0f, 28.0f))
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(STextBlock)
						.Text(FText::FromString(TEXT("系统菜单")))
						.Font(MenuFont(TreadUI::EFontRole::SansBlack, 40.0f))
						.ColorAndOpacity(TreadUI::Ink)
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.0f, 4.0f, 0.0f, 22.0f))
					[
						SNew(STextBlock)
						.Text(FText::FromString(TEXT("ПАУЗА  ·  PAUSE")))
						.Font(MenuFont(TreadUI::EFontRole::Russo, 15.0f))
						.ColorAndOpacity(TreadUI::Red)
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(STextBlock)
						.Text(FText::FromString(TEXT("当前对局会暂停。退出将直接关闭游戏。")))
						.Font(MenuFont(TreadUI::EFontRole::SansMedium, 17.0f))
						.ColorAndOpacity(TreadUI::InkA(0.72f))
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.0f, 24.0f, 0.0f, 0.0f))
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot()
						.FillWidth(1.0f)
						.Padding(FMargin(0.0f, 0.0f, 8.0f, 0.0f))
						[
							SNew(SButton)
							.ButtonColorAndOpacity(TreadUI::Red)
							.ContentPadding(FMargin(18.0f, 14.0f))
							.OnClicked_Lambda([this]() { OnQuit.ExecuteIfBound(); return FReply::Handled(); })
							[
								SNew(STextBlock)
								.Text(FText::FromString(TEXT("退出游戏")))
								.Font(MenuFont(TreadUI::EFontRole::SansBold, 22.0f))
								.ColorAndOpacity(FLinearColor::White)
								.Justification(ETextJustify::Center)
							]
						]
						+ SHorizontalBox::Slot()
						.FillWidth(1.0f)
						.Padding(FMargin(8.0f, 0.0f, 0.0f, 0.0f))
						[
							SNew(SButton)
							.ButtonColorAndOpacity(TreadUI::Ink)
							.ContentPadding(FMargin(18.0f, 14.0f))
							.OnClicked_Lambda([this]() { OnCancel.ExecuteIfBound(); return FReply::Handled(); })
							[
								SNew(STextBlock)
								.Text(FText::FromString(TEXT("取消")))
								.Font(MenuFont(TreadUI::EFontRole::SansBold, 22.0f))
								.ColorAndOpacity(TreadUI::Paper)
								.Justification(ETextJustify::Center)
							]
						]
					]
				]
			]
		]
	];
}
