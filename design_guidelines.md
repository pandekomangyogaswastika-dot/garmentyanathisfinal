{
  "meta": {
    "app_type": "dashboard",
    "module": "PDF Export Configuration (Presets)",
    "audience": "Garment factory ERP administrators",
    "design_personality": [
      "enterprise",
      "quietly premium",
      "high-clarity",
      "dense-data friendly",
      "settings-first (not marketing)"
    ],
    "north_star": "Make it effortless to create, audit, and switch PDF export presets without mistakes."
  },

  "brand_attributes": {
    "tone": ["trustworthy", "precise", "calm", "operational"],
    "visual_keywords": ["dark slate", "hairline borders", "soft elevation", "teal focus", "structured grids"],
    "anti_keywords": ["flashy", "neon", "heavy gradients", "centered landing-page layout"]
  },

  "typography": {
    "google_fonts": {
      "heading": {
        "family": "Space Grotesk",
        "weights": [500, 600, 700]
      },
      "body": {
        "family": "IBM Plex Sans",
        "weights": [400, 500, 600]
      },
      "mono": {
        "family": "IBM Plex Mono",
        "weights": [400, 500]
      }
    },
    "usage": {
      "page_title": "Space Grotesk 600",
      "section_titles": "Space Grotesk 600",
      "body": "IBM Plex Sans 400/500",
      "labels": "IBM Plex Sans 500",
      "column_keys_or_codes": "IBM Plex Mono 400"
    },
    "text_size_hierarchy": {
      "h1": "text-4xl sm:text-5xl lg:text-6xl",
      "h2": "text-base md:text-lg",
      "body": "text-sm md:text-base",
      "small": "text-xs md:text-sm"
    },
    "tailwind_font_classes": {
      "heading": "font-[\"Space Grotesk\"]",
      "body": "font-[\"IBM Plex Sans\"]",
      "mono": "font-[\"IBM Plex Mono\"]"
    },
    "notes": "Keep headings compact; settings pages should prioritize scanability over dramatic type."
  },

  "color_system": {
    "mode": "dark (slate)",
    "palette": {
      "bg": "#0B1220",
      "bg_2": "#0F172A",
      "surface": "#111C33",
      "surface_2": "#0F1A2E",
      "border": "#22314D",
      "border_subtle": "#1B2942",
      "text": "#E6EDF7",
      "text_muted": "#A7B4C8",
      "text_subtle": "#7F8CA3",
      "primary": "#2DD4BF",
      "primary_2": "#22C3AE",
      "primary_fg": "#06201C",
      "warning": "#FBBF24",
      "danger": "#F87171",
      "success": "#34D399",
      "focus_ring": "#5EEAD4"
    },
    "semantic_tokens_css": "/* Put in index.css or App.css under @layer base :root and .dark */\n:root {\n  --radius: 0.75rem;\n}\n.dark {\n  --background: 222 47% 8%; /* ~#0B1220 */\n  --foreground: 210 40% 96%;\n\n  --card: 222 44% 12%;\n  --card-foreground: 210 40% 96%;\n\n  --popover: 222 44% 12%;\n  --popover-foreground: 210 40% 96%;\n\n  --muted: 222 34% 16%;\n  --muted-foreground: 215 18% 72%;\n\n  --accent: 222 34% 16%;\n  --accent-foreground: 210 40% 96%;\n\n  --border: 217 33% 22%;\n  --input: 217 33% 22%;\n\n  --primary: 172 66% 50%; /* teal */\n  --primary-foreground: 173 70% 8%;\n\n  --ring: 172 76% 62%;\n\n  --destructive: 0 72% 52%;\n  --destructive-foreground: 210 40% 96%;\n\n  --sidebar-background: 222 47% 7%;\n  --sidebar-foreground: 210 40% 92%;\n  --sidebar-accent: 222 34% 14%;\n  --sidebar-accent-foreground: 210 40% 96%;\n  --sidebar-border: 217 33% 18%;\n  --sidebar-ring: 172 76% 62%;\n}",
    "gradient_policy": {
      "allowed": "Very subtle, large-area only, max 20% viewport; use as a top header wash behind page title.",
      "recommended_example": "background: radial-gradient(900px circle at 10% 0%, rgba(45,212,191,0.10), transparent 55%), radial-gradient(700px circle at 90% 10%, rgba(94,234,212,0.06), transparent 50%);",
      "prohibited": [
        "purple/pink combos",
        "dark saturated gradients",
        "gradients on cards/tables",
        "gradients on small UI elements"
      ]
    },
    "texture": {
      "noise_overlay": "Use a subtle CSS noise overlay on the page background only (opacity 0.035–0.06).",
      "css_snippet": ".app-noise::before{content:\"\";position:fixed;inset:0;pointer-events:none;background-image:url('data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22120%22 height=%22120%22%3E%3Cfilter id=%22n%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.9%22 numOctaves=%222%22 stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect width=%22120%22 height=%22120%22 filter=%22url(%23n)%22 opacity=%220.35%22/%3E%3C/svg%3E');opacity:.045;mix-blend-mode:overlay;}",
      "note": "Do not apply noise to modals or cards; keep it on the app shell only."
    }
  },

  "layout_and_grid": {
    "page_context": "Settings sub-page inside existing ERP sidebar layout.",
    "content_width": "max-w-6xl (centered within content area, but left-aligned text)",
    "page_padding": "px-4 sm:px-6 lg:px-8 py-6",
    "header_pattern": {
      "left": "Breadcrumb + Title + Description",
      "right": "PDF Type Select + New Preset button",
      "tailwind": "flex flex-col gap-3 md:flex-row md:items-end md:justify-between"
    },
    "main_split": {
      "desktop": "Two-column: left = presets list, right = column selector + preview",
      "tailwind": "grid grid-cols-1 lg:grid-cols-12 gap-6",
      "columns": {
        "left": "lg:col-span-4",
        "right": "lg:col-span-8"
      }
    },
    "spacing_rule": "Use 2–3x more spacing than default shadcn examples; prefer gap-4/6/8 over gap-2/3."
  },

  "components": {
    "component_path": {
      "shadcn": {
        "button": "/app/frontend/src/components/ui/button.jsx",
        "card": "/app/frontend/src/components/ui/card.jsx",
        "badge": "/app/frontend/src/components/ui/badge.jsx",
        "dialog": "/app/frontend/src/components/ui/dialog.jsx",
        "select": "/app/frontend/src/components/ui/select.jsx",
        "checkbox": "/app/frontend/src/components/ui/checkbox.jsx",
        "tabs": "/app/frontend/src/components/ui/tabs.jsx",
        "separator": "/app/frontend/src/components/ui/separator.jsx",
        "scroll_area": "/app/frontend/src/components/ui/scroll-area.jsx",
        "tooltip": "/app/frontend/src/components/ui/tooltip.jsx",
        "dropdown_menu": "/app/frontend/src/components/ui/dropdown-menu.jsx",
        "input": "/app/frontend/src/components/ui/input.jsx",
        "label": "/app/frontend/src/components/ui/label.jsx",
        "textarea": "/app/frontend/src/components/ui/textarea.jsx",
        "switch": "/app/frontend/src/components/ui/switch.jsx",
        "sonner": "/app/frontend/src/components/ui/sonner.jsx"
      }
    },

    "page_level_blocks": {
      "settings_shell": {
        "description": "Wrap content in a Card-like surface with subtle border; keep background as app shell.",
        "tailwind": "rounded-xl border border-border/70 bg-card/60 backdrop-blur-[2px]"
      },
      "pdf_type_select": {
        "component": "Select",
        "placement": "Header right",
        "tailwind": "w-full md:w-[260px]",
        "data_testid": "pdf-type-select"
      },
      "preset_list_panel": {
        "component": "Card + ScrollArea",
        "description": "Grouped by PDF type; each preset is a compact card row with actions.",
        "tailwind": "h-[calc(100vh-220px)] lg:h-[calc(100vh-200px)]",
        "data_testid": "preset-list-panel"
      },
      "column_selector_panel": {
        "component": "Card",
        "description": "Checkbox grid with search + bulk actions.",
        "data_testid": "column-selector-panel"
      },
      "preview_panel": {
        "component": "Card",
        "description": "Read-only preview of selected columns (chips + count + optional table preview).",
        "data_testid": "selected-columns-preview"
      }
    },

    "preset_card": {
      "structure": [
        "Left: preset name + small meta (created by/updated at optional)",
        "Right: Default badge + actions menu"
      ],
      "states": {
        "default": "border-border_subtle bg-surface",
        "active_selected": "ring-1 ring-primary/35 border-primary/30",
        "hover": "hover:bg-accent/40"
      },
      "tailwind": "group flex items-start justify-between gap-3 rounded-lg border bg-card/40 px-3 py-3",
      "micro_interactions": [
        "On hover: show kebab menu button (opacity transition)",
        "On click: highlight as active (ring)",
        "Default badge uses subtle teal outline"
      ],
      "data_testid": {
        "card": "preset-card",
        "set_default_button": "preset-set-default-button",
        "edit_button": "preset-edit-button",
        "delete_button": "preset-delete-button",
        "actions_menu": "preset-actions-menu"
      }
    },

    "column_selector_grid": {
      "layout": {
        "tailwind": "grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2",
        "cell": "flex items-start gap-2 rounded-md border border-border/60 bg-background/20 px-3 py-2"
      },
      "cell_content": {
        "left": "Checkbox",
        "right": "Column label + optional helper (source table / field key in mono)"
      },
      "bulk_actions": {
        "controls": ["Search", "Select all", "Clear", "Invert"],
        "tailwind": "flex flex-col gap-2 md:flex-row md:items-center md:justify-between"
      },
      "data_testid": {
        "search_input": "column-search-input",
        "select_all_button": "columns-select-all-button",
        "clear_button": "columns-clear-button",
        "invert_button": "columns-invert-button",
        "checkbox": "column-checkbox"
      },
      "notes": "Prefer indeterminate state for 'Select all' when some columns are selected."
    },

    "create_edit_preset_modal": {
      "component": "Dialog",
      "size": "max-w-[760px]",
      "layout": "Two sections: preset meta (name, default toggle) + column selector (scrollable)",
      "tailwind": "sm:rounded-xl",
      "footer": "Cancel (ghost) + Save preset (primary)",
      "data_testid": {
        "open_button": "preset-create-button",
        "dialog": "preset-dialog",
        "name_input": "preset-name-input",
        "default_switch": "preset-default-switch",
        "save_button": "preset-save-button",
        "cancel_button": "preset-cancel-button"
      }
    },

    "danger_zone": {
      "pattern": "AlertDialog for delete confirmation",
      "copy": {
        "title": "Delete preset?",
        "body": "This removes the preset configuration. This does not affect historical PDFs.",
        "confirm": "Delete preset"
      },
      "data_testid": {
        "delete_trigger": "preset-delete-trigger",
        "confirm": "preset-delete-confirm-button"
      }
    }
  },

  "buttons": {
    "style": "Professional / Corporate",
    "tokens": {
      "radius": "rounded-lg",
      "primary": "bg-primary text-primary-foreground hover:bg-primary/90",
      "secondary": "bg-secondary text-secondary-foreground hover:bg-secondary/80",
      "ghost": "hover:bg-accent hover:text-accent-foreground",
      "destructive": "bg-destructive text-destructive-foreground hover:bg-destructive/90"
    },
    "interaction": {
      "hover": "Use color/opacity shifts only (no transform on all elements).",
      "press": "active:scale-[0.99] only on primary CTA buttons",
      "focus": "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    },
    "do_not": ["Do not use transition-all", "Do not use gradients on buttons"]
  },

  "motion": {
    "library": {
      "recommended": "framer-motion",
      "install": "npm i framer-motion",
      "usage": "Use for subtle entrance (opacity + y) on panels and for list reordering/adding presets."
    },
    "principles": [
      "Motion should confirm state changes (saved, default set, deleted)",
      "Keep durations short: 140–220ms",
      "Use easing: cubic-bezier(0.2, 0.8, 0.2, 1)"
    ],
    "micro_interactions": {
      "preset_card_hover": "opacity transition for actions button: transition-opacity duration-150",
      "checkbox": "Use shadcn checkbox default check animation; add subtle ring on focus",
      "save_toast": "Use sonner toast with concise copy and optional 'Undo' for delete"
    }
  },

  "data_dense_patterns": {
    "preview": {
      "chips": "Show selected columns as Badge chips (variant=secondary) with max 2 lines + 'View all'",
      "count": "Always show count: e.g., '12 columns selected'",
      "optional_table": "If needed, show a small Table preview with 3 sample rows (Skeleton while loading)."
    },
    "empty_states": {
      "no_presets": {
        "title": "No presets yet",
        "body": "Create a preset to standardize PDF exports for this type.",
        "cta": "New preset"
      },
      "no_columns_match": {
        "title": "No columns match your search",
        "body": "Try a different keyword or clear the filter."
      }
    }
  },

  "accessibility": {
    "requirements": [
      "WCAG AA contrast for text on dark surfaces",
      "Keyboard navigation for Select, Dialog, Checkbox grid",
      "Visible focus ring using --ring token",
      "Use aria-label on icon-only buttons",
      "Do not rely on color alone for default indicator (use Badge + icon)"
    ],
    "checkbox_grid_a11y": "Each checkbox label must be clickable; wrap with <Label htmlFor>. Provide helper text via aria-describedby when showing field keys.",
    "reduced_motion": "Respect prefers-reduced-motion: disable entrance animations and keep only instant state changes."
  },

  "icons": {
    "library": "lucide-react",
    "recommended": {
      "pdf_type": "FileText",
      "preset": "SlidersHorizontal",
      "default": "Star",
      "delete": "Trash2",
      "edit": "Pencil",
      "preview": "Eye",
      "more": "MoreVertical",
      "search": "Search"
    },
    "icon_button_style": "Use ghost buttons with 32–36px hit area: h-9 w-9 p-0"
  },

  "images": {
    "image_urls": [],
    "note": "This is an ERP settings module; avoid decorative photography. Use icons + subtle texture only."
  },

  "implementation_scaffolds_js": {
    "page_skeleton": "// PDFConfigPage.jsx\n// Layout assumes existing ERP sidebar shell wraps this page\n\nimport React from 'react'\nimport { Card, CardHeader, CardTitle, CardDescription, CardContent } from './components/ui/card'\nimport { Button } from './components/ui/button'\nimport { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from './components/ui/select'\nimport { ScrollArea } from './components/ui/scroll-area'\n\nexport default function PDFConfigPage() {\n  return (\n    <div className=\"app-noise\">\n      <div className=\"px-4 sm:px-6 lg:px-8 py-6\">\n        <div className=\"flex flex-col gap-3 md:flex-row md:items-end md:justify-between\">\n          <div>\n            <div className=\"text-xs text-muted-foreground\" data-testid=\"pdf-config-breadcrumb\">Settings / PDF Export</div>\n            <h1 className=\"mt-1 font-semibold tracking-tight text-2xl md:text-3xl\" data-testid=\"pdf-config-page-title\">PDF Export Presets</h1>\n            <p className=\"mt-1 text-sm text-muted-foreground\" data-testid=\"pdf-config-page-description\">Choose columns per PDF type, save presets, and set defaults.</p>\n          </div>\n\n          <div className=\"flex w-full flex-col gap-2 md:w-auto md:flex-row md:items-center\">\n            <div className=\"w-full md:w-[260px]\" data-testid=\"pdf-type-select\">\n              <Select>\n                <SelectTrigger>\n                  <SelectValue placeholder=\"Select PDF type\" />\n                </SelectTrigger>\n                <SelectContent>\n                  <SelectItem value=\"production-po\">Production PO</SelectItem>\n                  <SelectItem value=\"vendor-shipment\">Vendor Shipment</SelectItem>\n                  <SelectItem value=\"reports\">Reports</SelectItem>\n                </SelectContent>\n              </Select>\n            </div>\n            <Button data-testid=\"preset-create-button\">New preset</Button>\n          </div>\n        </div>\n\n        <div className=\"mt-6 grid grid-cols-1 lg:grid-cols-12 gap-6\">\n          <Card className=\"lg:col-span-4\" data-testid=\"preset-list-panel\">\n            <CardHeader>\n              <CardTitle className=\"text-base\">Presets</CardTitle>\n              <CardDescription>Saved configurations by PDF type.</CardDescription>\n            </CardHeader>\n            <CardContent>\n              <ScrollArea className=\"h-[calc(100vh-260px)]\">\n                {/* preset cards */}\n              </ScrollArea>\n            </CardContent>\n          </Card>\n\n          <div className=\"lg:col-span-8 space-y-6\">\n            <Card data-testid=\"column-selector-panel\">\n              <CardHeader>\n                <CardTitle className=\"text-base\">Columns</CardTitle>\n                <CardDescription>Select which columns appear in the PDF.</CardDescription>\n              </CardHeader>\n              <CardContent>\n                {/* search + bulk actions + checkbox grid */}\n              </CardContent>\n            </Card>\n\n            <Card data-testid=\"selected-columns-preview\">\n              <CardHeader>\n                <CardTitle className=\"text-base\">Preview</CardTitle>\n                <CardDescription>Review selected columns before saving.</CardDescription>\n              </CardHeader>\n              <CardContent>\n                {/* chips + count */}\n              </CardContent>\n            </Card>\n          </div>\n        </div>\n      </div>\n    </div>\n  )\n}\n",
    "column_cell": "// ColumnCheckboxCell.jsx\nimport React from 'react'\nimport { Checkbox } from './components/ui/checkbox'\nimport { Label } from './components/ui/label'\n\nexport function ColumnCheckboxCell({ id, label, fieldKey, checked, onChange }) {\n  return (\n    <div className=\"flex items-start gap-2 rounded-md border border-border/60 bg-background/20 px-3 py-2\">\n      <Checkbox\n        id={id}\n        checked={checked}\n        onCheckedChange={onChange}\n        data-testid=\"column-checkbox\"\n      />\n      <div className=\"min-w-0\">\n        <Label htmlFor={id} className=\"cursor-pointer\">{label}</Label>\n        {fieldKey ? (\n          <div className=\"mt-0.5 text-xs text-muted-foreground font-mono\">{fieldKey}</div>\n        ) : null}\n      </div>\n    </div>\n  )\n}\n"
  },

  "instructions_to_main_agent": [
    "Keep the module visually consistent with existing ERP dark slate theme; do not introduce bright gradients or marketing-like hero sections.",
    "Implement the page as a settings sub-page: breadcrumb, title, short description, then split layout (presets left, configuration right).",
    "Use shadcn/ui components from /app/frontend/src/components/ui (Button, Card, Dialog, Select, Checkbox, ScrollArea, Badge, DropdownMenu, AlertDialog).",
    "All interactive and key informational elements MUST include data-testid attributes (kebab-case).",
    "Avoid transition: all. Use targeted transitions like transition-colors, transition-opacity.",
    "Use teal as the only accent (primary). Use yellow only for warnings and red for destructive actions.",
    "Default preset indicator: show a Badge + Star icon; also reflect in actions menu ('Set as default' disabled when already default).",
    "Column selector grid must be responsive and scroll-friendly; include search + bulk actions.",
    "Use sonner toasts for save/delete feedback; include Undo for delete if feasible."
  ],

  "appendix_general_ui_ux_design_guidelines": "<General UI UX Design Guidelines>\n    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms\n    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text\n   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json\n\n **GRADIENT RESTRICTION RULE**\nNEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc\nNEVER use dark gradients for logo, testimonial, footer etc\nNEVER let gradients cover more than 20% of the viewport.\nNEVER apply gradients to text-heavy content or reading areas.\nNEVER use gradients on small UI elements (<100px width).\nNEVER stack multiple gradient layers in the same viewport.\n\n**ENFORCEMENT RULE:**\n    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors\n\n**How and where to use:**\n   • Section backgrounds (not content backgrounds)\n   • Hero section header content. Eg: dark to light to dark color\n   • Decorative overlays and accent elements only\n   • Hero section with 2-3 mild color\n   • Gradients creation can be done for any angle say horizontal, vertical or diagonal\n\n- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**\n\n</Font Guidelines>\n\n- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. \n   \n- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.\n\n- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.\n   \n- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly\n    Eg: - if it implies playful/energetic, choose a colorful scheme\n           - if it implies monochrome/minimal, choose a black–white/neutral scheme\n\n**Component Reuse:**\n\t- Prioritize using pre-existing components from src/components/ui when applicable\n\t- Create new components that match the style and conventions of existing components when needed\n\t- Examine existing components to understand the project's component patterns before creating new ones\n\n**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component\n\n**Best Practices:**\n\t- Use Shadcn/UI as the primary component library for consistency and accessibility\n\t- Import path: ./components/[component-name]\n\n**Export Conventions:**\n\t- Components MUST use named exports (export const ComponentName = ...)\n\t- Pages MUST use default exports (export default function PageName() {...})\n\n**Toasts:**\n  - Use `sonner` for toasts\"\n  - Sonner component are located in `/app/src/components/ui/sonner.tsx`\n\nUse 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.\n</General UI UX Design Guidelines>"
}
