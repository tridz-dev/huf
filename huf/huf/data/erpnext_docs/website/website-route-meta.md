---
title: "Website Route Meta"
source_url: "https://docs.frappe.io/erpnext/website-route-meta"
section: website
---

# Website Route Meta

Arbitrary meta tags can be added to web pages using Website Route Meta. Meta tags are invisible tags that provide data about your page to search engines and website visitors. "When used correctly, these tags may help boost your SEO and rankings on popular search engines." These tags will be placed in the `<head>` section of your page. ERPNext allows you to add arbitrary meta tags in your web pages to improve the SEO of your pages.

To access Website Route Meta go to:

> Home > Website > Web Site > Website Route Meta

## 1. How to add meta tags to a web page

1. Go to the Website Route Meta list and click on New.
1. Enter the route. Make sure the route doesn't start with a slash (`/`). A Web Page for this route should exist.
1. Add key value pairs for each meta tag. For e.g., to add keywords to your web page, enter "keywords" as the Key and add comma separated keywords in the Value column.
1. Click on Save.

![New Website Route Meta](/files/new-website-route-meta.png)
*New Website Route Meta*

Now if you check the page source of your web page, the meta tags will look something like this:

```html
<meta name="keywords" content="keyword1, keyword2, keyword3">
```

> **Note:** Meta Tags are not only limited to Web Page, but they can be added to any route that has a website page in ERPNext.
>
> For e.g., You can add meta tags to your blog posts if you know the route which you can get from the Blog Post form.
