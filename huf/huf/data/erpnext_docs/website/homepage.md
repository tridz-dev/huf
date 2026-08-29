---
title: "Homepage"
source_url: "https://docs.frappe.io/erpnext/homepage"
section: website
---

# Homepage

**A homepage is the default landing page of your website.**

ERPNext's Website Module generates a default landing page for your website. You can customize it in Homepage.

To access the Homepage page in ERPNext, go to:

> Home > Website > Portal > Homepage

## 1. How to setup Home Page
1. Select the Company.
1. Set the Title. This will be shown in the Browser Tab.
1. Configure the Hero Section as explained in the next section.

> Make sure your default 'Home Page' is set as `home` in Website Settings for this to work.

## 2. Hero Section

There are three ways in which you can customize the way the Hero Section looks:

1. Tag Line and Description (Default).
1. Homepage Slideshow.
1. Custom Hero Section.

### 2.1 Tag Line and Description

After you set your Tag Line, Description and Hero Image you'll have a decent looking front page. You can also change the URL for the Explore button under **URL for "All Products"**.

### 2.2 Homepage Slideshow

Set the **Hero Section Based On** to **Slideshow** and the **Homepage Slideshow** field will appear.

Now, select an existing Slideshow or create a new one shown as follows:

> For best results, make sure all of your slideshow images have same height and their width is greater than the height.

### 2.3 Custom Hero Section

The third type of Hero Section allows you to write your own HTML.

Set **Hero Section Based On** to **Hero Section**.

Now create a new Hero Section. Set **Section Based On** as **Custom HTML**. Write your custom HTML in the Section HTML field.

You can write any valid [Bootstrap 4](https://getbootstrap.com/) markup here.

## 3. Featured Products

You can also show featured products on your Homepage by adding them to the Products table.

## 4. Homepage Section

You can add custom sections on your Homepage by creating new Homepage Sections.

> Go to Website > Portal > Homepage Section

A homepage section can consist of cards or Custom HTML. Set **Section Based On** to **Cards**.

Add details for each card like Title, Subtitle, Image, Content and Route in the Section Cards table.

You can also control the order in which these sections appear by setting the **Section Order**. 0 will be shown first, followed by 1, and so on.

> To add Sections with Custom HTML refer [Custom Hero Section](#23-custom-hero-section).

## 5. Custom Homepage

ERPNext allows you to have a completely different homepage if you don't want to use the default one described above.

To setup a custom homepage:

1. Create a [Web Page](/erpnext/web-page).
1. Go to Website > Setup > Website Settings.
1. Set Home Page as the `route` of your Web Page.
